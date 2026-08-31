#!/usr/bin/env python3
"""Turn checkpointed Mistral OCR responses into Starlight Markdown pages."""

from __future__ import annotations

import base64
import gzip
import json
import mimetypes
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "ocr" / "chunks"
REPORTS = ROOT / "data" / "ocr" / "reports"
DOCS = ROOT / "src" / "content" / "docs"
PUBLIC = ROOT / "public"
ASSETS = ROOT / "public" / "book" / "assets"
POLONA_URL = "https://polona.pl/item-view/0782bd3a-4d20-41be-86f8-bcdfc65555c5?page=0"
BASE = "/harcerz-w-polu"
PUBLIC_SITE = "https://jfpio.github.io/harcerz-w-polu"

GAME_HEADING = re.compile(
    r"^\s*#{1,6}\s+(?:\*\*)?(?P<number>\d{1,3})[.)]\s+(?P<title>.+?)(?:\*\*)?\s*$"
)


@dataclass(frozen=True)
class Line:
    text: str
    pdf_page: int


@dataclass(frozen=True)
class Game:
    number: int
    title: str
    start: int
    end: int
    section_key: str
    section_label: str
    for_older: bool


SECTIONS = [
    (1, 18, "orientowanie", "Orientowanie się w terenie"),
    (19, 57, "wzrok-spostrzegawczosc", "Wzrok i spostrzegawczość"),
    (58, 65, "sluch", "Słuch"),
    (66, 107, "zwiady", "Zwiady"),
    (108, 117, "wiekszy-zespol", "Ćwiczenia w większym zespole"),
]

SECTION_TITLES = {
    "orientowanie": "ORIENTOWANIE SIĘ W TERENIE",
    "wzrok-spostrzegawczosc": "WZROK",
    "sluch": "SŁUCH",
    "zwiady": "ZWIADY",
    "wiekszy-zespol": "ĆWICZENIA W WIĘKSZYM ZESPOLE",
}

TITLE_OCR_CORRECTIONS = {
    53: "Fałszywe tropy",
    72: "Trop w trop za wrogiem",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    ascii_value = ascii_value.lower().replace("ł", "l")
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return ascii_value or "strona"


def normalized_heading(value: str) -> str:
    value = re.sub(r"^#{1,6}\s+", "", value).replace("**", "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def safe_asset_name(page_index: int, image_id: str, media_type: str) -> str:
    source_name = Path(image_id).name
    suffix = Path(source_name).suffix or mimetypes.guess_extension(media_type) or ".bin"
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(source_name).stem).strip("-") or "image"
    return f"page-{page_index + 1:03d}-{stem}{suffix.lower()}"


def load_pages() -> list[dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    for chunk_path in sorted(CHUNKS.glob("pages-*.json.gz")):
        with gzip.open(chunk_path, "rt", encoding="utf-8") as stream:
            response = json.load(stream)
        for page in response.get("pages", []):
            index = int(page["index"])
            if index in pages:
                raise RuntimeError(f"Duplicate OCR page: {index}")
            pages[index] = page
    expected = list(range(260))
    if sorted(pages) != expected:
        missing = sorted(set(expected) - set(pages))
        raise RuntimeError(f"OCR is incomplete; missing page indexes: {missing}")
    return [pages[index] for index in expected]


def materialize_images(page: dict[str, Any]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for image in page.get("images", []):
        image_id = str(image.get("id", "image"))
        encoded = image.get("image_base64")
        media_type = "application/octet-stream"
        if encoded and encoded.startswith("data:"):
            header, encoded_data = encoded.split(",", 1)
            media_type = header[5:].split(";", 1)[0]
            target_name = safe_asset_name(int(page["index"]), image_id, media_type)
            target = ASSETS / target_name
            if not target.exists():
                target.write_bytes(base64.b64decode(encoded_data))
        else:
            target_name = safe_asset_name(int(page["index"]), image_id, media_type)
        replacements[image_id] = f"{BASE}/book/assets/{target_name}"
    return replacements


def page_markdown(page: dict[str, Any]) -> str:
    markdown = str(page.get("markdown", ""))
    for image_id, target in materialize_images(page).items():
        markdown = markdown.replace(f"]({image_id})", f"]({target})")
    return markdown.strip()


def build_lines(pages: list[dict[str, Any]]) -> list[Line]:
    lines: list[Line] = []
    for page in pages:
        pdf_page = int(page["index"]) + 1
        for text in page_markdown(page).splitlines():
            lines.append(Line(text.rstrip(), pdf_page))
        lines.append(Line("", pdf_page))
    return lines


def section_for_game(number: int) -> tuple[str, str]:
    for start, end, key, label in SECTIONS:
        if start <= number <= end:
            return key, label
    raise ValueError(f"Unsupported game number: {number}")


def find_sequential_games(lines: list[Line]) -> list[tuple[int, int, str, bool]]:
    matches: list[tuple[int, int, str, bool]] = []
    expected = 1
    for index, line in enumerate(lines):
        match = GAME_HEADING.match(line.text)
        if not match or int(match.group("number")) != expected:
            continue
        raw_title = match.group("title").strip()
        for_older = bool(re.search(r"(?:\\?\*|\(dla starszych\))\s*$", raw_title, flags=re.I))
        title = re.sub(r"(?:\\?\*|\(dla starszych\))\s*$", "", raw_title, flags=re.I).strip()
        title = title.strip("*_ ")
        title = TITLE_OCR_CORRECTIONS.get(expected, title)
        if title.isupper():
            title = title.capitalize()
        matches.append((expected, index, title, for_older))
        expected += 1
        if expected == 118:
            break
    if expected != 118:
        found = [number for number, *_ in matches]
        raise RuntimeError(f"Expected games 1-117, found {len(matches)} sequential headings: {found}")
    return matches


def toc_older_numbers(lines: list[Line]) -> set[int]:
    result: set[int] = set()
    for line in lines:
        if line.pdf_page < 249 or "*" not in line.text:
            continue
        match = re.search(r"(?:^|\s)(\d{1,3})[.)]\s+.*?\\?\*", line.text)
        if match:
            number = int(match.group(1))
            if 1 <= number <= 117:
                result.add(number)
    return result


def find_section_heading(lines: list[Line], key: str, before_index: int) -> int:
    target = normalized_heading(SECTION_TITLES[key])
    candidates: list[int] = []
    for index, line in enumerate(lines[:before_index]):
        current = normalized_heading(line.text)
        if key == "wzrok-spostrzegawczosc":
            matched = current.startswith("WZROK") and "SPOSTRZEGAWCZOSC" in current
        else:
            matched = current == target
        if matched:
            candidates.append(index)
    if not candidates:
        raise RuntimeError(f"Section heading not found: {SECTION_TITLES[key]}")
    return candidates[-1]


def find_toc_start(lines: list[Line], after_index: int) -> int:
    for index in range(after_index, len(lines)):
        heading = normalized_heading(lines[index].text)
        if heading in {"TRESC", "SPIS TRESCI"}:
            return index
    for index in range(after_index, len(lines)):
        if lines[index].pdf_page >= 249:
            return index
    return len(lines)


def clean_body(lines: Iterable[Line], *, drop_first_heading: bool = False) -> str:
    values = [line.text for line in lines]
    if drop_first_heading:
        while values and not values[0].strip():
            values.pop(0)
        if values:
            values.pop(0)
    text = "\n".join(values).strip()
    # One running title was read into the middle of the word "mapie" on PDF page 55.
    text = re.sub(r"na\s+marcerz w polu\s+pie", "na mapie", text, flags=re.I)
    # Join words split typographically at the end of a scanned line or page.
    text = re.sub(r"(?<=\w)-\n{1,2}(?=[a-ząćęłńóśźż])", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def page_range(lines: Iterable[Line]) -> list[int]:
    pages = sorted({line.pdf_page for line in lines if line.text.strip()})
    return list(range(pages[0], pages[-1] + 1)) if pages else []


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def source_note(pdf_pages: list[int]) -> str:
    if not pdf_pages:
        return ""
    page_label = str(pdf_pages[0]) if len(pdf_pages) == 1 else f"{pdf_pages[0]}–{pdf_pages[-1]}"
    return (
        "\n\n---\n\n"
        f"*Źródło skanu: [Polona / Biblioteka Narodowa]({POLONA_URL}), "
        f"oznaczenie „Domena publiczna”. [Zobacz skan — strony PDF {page_label}]"
        f"({BASE}/book/harcerz-w-polu.pdf#page={pdf_pages[0]}).*\n"
    )


def write_document(path: Path, frontmatter: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\n" + "\n".join(frontmatter) + "\n---\n\n" + body.strip() + "\n"
    path.write_text(content, encoding="utf-8")


def make_games(lines: list[Line]) -> list[Game]:
    headings = find_sequential_games(lines)
    older_from_toc = toc_older_numbers(lines)
    section_starts: dict[str, int] = {}
    for start, _, key, _ in SECTIONS:
        first_heading_index = next(index for number, index, *_ in headings if number == start)
        section_starts[key] = find_section_heading(lines, key, first_heading_index)
    toc_start = find_toc_start(lines, headings[-1][1])

    games: list[Game] = []
    for position, (number, start_index, title, older_in_heading) in enumerate(headings):
        next_index = headings[position + 1][1] if position + 1 < len(headings) else toc_start
        key, label = section_for_game(number)
        if position + 1 < len(headings):
            next_number = headings[position + 1][0]
            next_key, _ = section_for_game(next_number)
            if next_key != key:
                next_index = section_starts[next_key]
        games.append(
            Game(
                number=number,
                title=title,
                start=start_index,
                end=next_index,
                section_key=key,
                section_label=label,
                for_older=older_in_heading or number in older_from_toc,
            )
        )
    return games


def write_games(lines: list[Line], games: list[Game]) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for game in games:
        segment = lines[game.start : game.end]
        pdf_pages = page_range(segment)
        printed_pages = [page - 6 for page in pdf_pages if page - 6 > 0]
        slug = f"{game.number:03d}-{slugify(game.title)}"
        route = f"gry/{game.section_key}/{slug}"
        filename = DOCS / "gry" / game.section_key / f"{slug}.md"
        body = clean_body(segment, drop_first_heading=True)
        beta = (
            "> **Transkrypcja OCR — wersja beta.** Tekst zachowuje pisownię wydania z 1946 roku. "
            "Jeżeli zauważysz błąd rozpoznania, użyj odsyłacza „Edytuj stronę” na dole.\n\n"
        )
        if game.for_older:
            beta += "> **Gra oznaczona w książce gwiazdką:** odpowiedniejsza dla starszych harcerzy.\n\n"
        frontmatter = [
            f"title: {yaml_string(f'{game.number}. {game.title}')}",
            f"description: {yaml_string(f'Gra terenowa nr {game.number} z książki Zygmunta Wyrobka.')}",
            f"slug: {yaml_string(route)}",
            f"number: {game.number}",
            f"section: {yaml_string(game.section_label)}",
            f"order: {game.number}",
            f"printedPages: {json.dumps(printed_pages)}",
            f"pdfPages: {json.dumps(pdf_pages)}",
            f"forOlderScouts: {'true' if game.for_older else 'false'}",
            "status: ocr-beta",
            f"sourceUrl: {yaml_string(POLONA_URL)}",
            "sidebar:",
            f"  order: {game.number}",
            f"  label: {yaml_string(f'{game.number}. {game.title}')}",
        ]
        write_document(filename, frontmatter, beta + body + source_note(pdf_pages))
        index.append(
            {
                "number": game.number,
                "title": game.title,
                "section": game.section_label,
                "sectionKey": game.section_key,
                "route": route,
                "pdfPages": pdf_pages,
                "printedPages": printed_pages,
                "forOlderScouts": game.for_older,
            }
        )
    return index


def find_heading(lines: list[Line], title: str, *, after: int = 0) -> int:
    target = normalized_heading(title)
    for index in range(after, len(lines)):
        if normalized_heading(lines[index].text) == target:
            return index
    raise RuntimeError(f"Heading not found: {title}")


def write_intro_documents(lines: list[Line], games: list[Game]) -> None:
    boundaries = [
        ("01-przedmowy.md", "Przedmowy do wydań", "PRZEDMOWA DO I WYDANIA", "OD WYDAWNICTWA"),
        ("02-od-wydawnictwa.md", "Od Wydawnictwa", "OD WYDAWNICTWA", "ZNACZENIE GIER TERENOWYCH"),
        (
            "03-znaczenie-gier-terenowych.md",
            "Znaczenie gier terenowych",
            "ZNACZENIE GIER TERENOWYCH",
            "WSKAZÓWKI METODYCZNE",
        ),
        (
            "04-wskazowki-metodyczne.md",
            "Wskazówki metodyczne",
            "WSKAZÓWKI METODYCZNE",
            "ORIENTOWANIE SIĘ W TERENIE",
        ),
    ]
    for order, (filename, title, start_title, end_title) in enumerate(boundaries, start=1):
        start = find_heading(lines, start_title)
        end = find_heading(lines, end_title, after=start + 1)
        segment = lines[start:end]
        pdf_pages = page_range(segment)
        frontmatter = [
            f"title: {yaml_string(title)}",
            f"description: {yaml_string(f'{title} — Harcerz w polu, wydanie z 1946 roku.')}",
            f"sidebar:\n  order: {order}",
            "status: ocr-beta",
            f"sourceUrl: {yaml_string(POLONA_URL)}",
        ]
        beta = "> **Transkrypcja OCR — wersja beta.** Zachowano historyczną pisownię wydania.\n\n"
        write_document(
            DOCS / "wprowadzenie" / filename,
            frontmatter,
            beta + clean_body(segment) + source_note(pdf_pages),
        )

    for section_start, _, key, label in SECTIONS:
        first_game = next(game for game in games if game.number == section_start)
        section_heading = find_section_heading(lines, key, first_game.start)
        segment = lines[section_heading:first_game.start]
        if not clean_body(segment):
            continue
        pdf_pages = page_range(segment)
        frontmatter = [
            f"title: {yaml_string(label)}",
            f"description: {yaml_string(f'Wprowadzenie do działu „{label}”.')}",
            f"slug: {yaml_string(f'gry/{key}')}",
            "sidebar:\n  order: 0\n  label: Wprowadzenie",
            "status: ocr-beta",
            f"sourceUrl: {yaml_string(POLONA_URL)}",
        ]
        write_document(
            DOCS / "gry" / key / "000-wprowadzenie.md",
            frontmatter,
            "> **Transkrypcja OCR — wersja beta.** Zachowano historyczną pisownię wydania.\n\n"
            + clean_body(segment)
            + source_note(pdf_pages),
        )


def write_index(game_index: list[dict[str, Any]]) -> None:
    first_game = game_index[0]
    frontmatter = [
        "title: Harcerz w polu",
        "description: Cyfrowa transkrypcja książki Zygmunta Wyrobka „Harcerz w polu. Zabawy i gry terenowe”.",
        "pagefind: false",
        "editUrl: false",
    ]
    body = f"""
<img class="book-cover-inline" src="{BASE}/book/cover.png" alt="Okładka piątego wydania książki Harcerz w polu" />

**Zabawy i gry terenowe — cyfrowa transkrypcja piątego wydania z 1946 roku.**

<p class="book-actions">
  <a href="{BASE}/wprowadzenie/01-przedmowy/">Czytaj od początku</a>
  <a href="{BASE}/{first_game['route']}/">Przeglądaj gry</a>
  <a href="{POLONA_URL}">Zobacz w Polonie</a>
  <a href="{BASE}/book/harcerz-w-polu.pdf">Pobierz oryginalny PDF</a>
</p>

## Wydanie cyfrowe

To publiczna wersja beta wiernej transkrypcji książki **Zygmunta Wyrobka**, wydanej w Krakowie przez Wydawnictwo Zakładu Narodowego imienia Ossolińskich w 1946 roku.

Książka obejmuje **117 zabaw, ćwiczeń i gier terenowych**. Każda gra ma własny adres, odsyłacz do właściwych stron skanu i możliwość zaproponowania korekty na GitHubie.

## Użycie z modelami językowymi

Najprostszy wariant to podać modelowi link do pełnej wersji tekstowej albo Markdown:

- [Instrukcja dla modeli i indeks linków]({BASE}/llms.txt)
- [Pełna transkrypcja w Markdown]({BASE}/book/harcerz-w-polu.md)
- [Pełna transkrypcja w TXT]({BASE}/book/harcerz-w-polu.txt)

## Źródło i prawa

Skan pobrano z [Polony / Biblioteki Narodowej]({POLONA_URL}). Rekord Polony oznacza obiekt jako **„Domena publiczna”**. Tekst pozyskano przy użyciu Mistral OCR; pisowni wydania nie modernizowano.

> **Status: transkrypcja OCR — wersja beta.** Błędy rozpoznania można poprawiać przez odsyłacz „Edytuj stronę”.
"""
    write_document(DOCS / "index.mdx", frontmatter, body)


def strip_frontmatter(markdown: str) -> str:
    if markdown.startswith("---\n"):
        _, _, rest = markdown.partition("\n---\n")
        return rest.strip()
    return markdown.strip()


def plain_text(markdown: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^>\s?", "", text, flags=re.M)
    text = re.sub(r"[*_`#]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def write_llm_exports(game_index: list[dict[str, Any]]) -> None:
    ordered_docs = [
        DOCS / "wprowadzenie" / "01-przedmowy.md",
        DOCS / "wprowadzenie" / "02-od-wydawnictwa.md",
        DOCS / "wprowadzenie" / "03-znaczenie-gier-terenowych.md",
        DOCS / "wprowadzenie" / "04-wskazowki-metodyczne.md",
    ]
    ordered_docs.extend(DOCS / f"{game['route']}.md" for game in game_index)

    sections = [
        "# Harcerz w polu. Zabawy i gry terenowe",
        "",
        "Zygmunt Wyrobek, wydanie piąte, Kraków 1946.",
        f"Źródło skanu: Polona / Biblioteka Narodowa, {POLONA_URL}.",
        "Prawa: rekord Polony oznacza obiekt jako „Domena publiczna”.",
        "Status transkrypcji: OCR beta, bez modernizacji języka i pisowni.",
        "",
    ]
    for path in ordered_docs:
        if not path.exists():
            raise RuntimeError(f"Missing generated document for LLM export: {path}")
        sections.append(strip_frontmatter(path.read_text(encoding="utf-8")))
        sections.append("")

    full_markdown = "\n".join(sections).strip() + "\n"
    book_dir = PUBLIC / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "harcerz-w-polu.md").write_text(full_markdown, encoding="utf-8")
    (book_dir / "harcerz-w-polu.txt").write_text(plain_text(full_markdown) + "\n", encoding="utf-8")
    (PUBLIC / "llms-full.txt").write_text(full_markdown, encoding="utf-8")

    llms = f"""# Harcerz w polu

Cyfrowa transkrypcja książki: Zygmunt Wyrobek, „Harcerz w polu. Zabawy i gry terenowe”, wydanie piąte, Kraków 1946.

Źródło skanu: Polona / Biblioteka Narodowa, {POLONA_URL}.
Prawa: rekord Polony oznacza obiekt jako „Domena publiczna”.
Status: transkrypcja OCR beta wykonana przy użyciu Mistral OCR, bez modernizacji języka i pisowni.

## Najważniejsze linki

- Strona WWW: {PUBLIC_SITE}/
- Pełna transkrypcja Markdown: {PUBLIC_SITE}/book/harcerz-w-polu.md
- Pełna transkrypcja TXT: {PUBLIC_SITE}/book/harcerz-w-polu.txt
- Pełna transkrypcja jako llms-full.txt: {PUBLIC_SITE}/llms-full.txt
- Indeks 117 gier JSON: {PUBLIC_SITE}/book/games.json
- Oryginalny PDF: {PUBLIC_SITE}/book/harcerz-w-polu.pdf
- Rekord Polony: {POLONA_URL}

## Sugerowane użycie

Do analizy całej książki użyj najpierw `llms-full.txt` albo pełnego pliku Markdown. Do cytowania konkretnych gier korzystaj z adresów stron WWW lub z indeksu JSON.
"""
    (PUBLIC / "llms.txt").write_text(llms, encoding="utf-8")
    robots = f"""# Source: {POLONA_URL}
User-agent: *
Allow: /harcerz-w-polu/

Sitemap: {PUBLIC_SITE}/sitemap-index.xml
LLMs: {PUBLIC_SITE}/llms.txt
LLMs-Full: {PUBLIC_SITE}/llms-full.txt
"""
    (PUBLIC / "robots.txt").write_text(robots, encoding="utf-8")
    public_game_index = {
        "title": "Harcerz w polu. Zabawy i gry terenowe",
        "sourceUrl": POLONA_URL,
        "rightsStatement": "Domena publiczna według rekordu Polony",
        "status": "ocr-beta",
        "games": game_index,
    }
    (book_dir / "games.json").write_text(
        json.dumps(public_game_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_table_of_contents(game_index: list[dict[str, Any]]) -> None:
    frontmatter = [
        "title: Spis treści",
        "description: Wszystkie 117 gier i ćwiczeń terenowych.",
        "editUrl: false",
    ]
    parts = [
        "Wykaz gier na podstawie spisu treści piątego wydania. Gwiazdką oznaczono gry odpowiedniejsze dla starszych harcerzy.",
    ]
    for _, _, key, label in SECTIONS:
        parts.append(f"\n## {label}\n")
        for game in [item for item in game_index if item["sectionKey"] == key]:
            star = r" \*" if game["forOlderScouts"] else ""
            parts.append(f"{game['number']}. [{game['title']}]({BASE}/{game['route']}/){star}")
    write_document(
        DOCS / "spis-tresci.md",
        frontmatter,
        "\n".join(parts) + source_note([249, 250, 251, 252]),
    )


def write_about() -> None:
    frontmatter = [
        "title: O wydaniu cyfrowym",
        "description: Pochodzenie skanu, zasady transkrypcji i sposób zgłaszania korekt.",
    ]
    body = f"""
## Informacja bibliograficzna

**Zygmunt Wyrobek, „Harcerz w polu. Zabawy i gry terenowe”, wydanie piąte, Kraków 1946, Wydawnictwo Zakładu Narodowego imienia Ossolińskich.**

## Źródło skanu i prawa

Książkę pobrano z [biblioteki cyfrowej Polona]({POLONA_URL}), prowadzonej przez Bibliotekę Narodową. Rekord źródłowy oznacza obiekt jako **„Domena publiczna”**. Ta strona zachowuje odsyłacz do rekordu zamiast zastępować go własną deklaracją licencyjną.

- [Zobacz książkę w Polonie]({POLONA_URL})
- [Pobierz użyty plik PDF]({BASE}/book/harcerz-w-polu.pdf)

## Jak powstała transkrypcja

Tekst rozpoznano za pomocą **Mistral OCR 4.1**. Surowe wyniki zapisano stronami wraz z ocenami pewności i informacją o układzie dokumentu. Następnie tekst podzielono na rozdziały i 117 osobnych gier.

Zachowujemy pisownię oraz język wydania z 1946 roku. Poprawiamy jedynie błędy rozpoznania; nie modernizujemy słownictwa ani interpunkcji.

## Publiczna beta i korekty

Transkrypcja ma status publicznej wersji beta. Na dole każdej strony znajduje się odsyłacz **„Edytuj stronę”**, który prowadzi do odpowiadającego jej pliku Markdown w repozytorium GitHub.
"""
    write_document(DOCS / "o-wydaniu.md", frontmatter, body)


def write_quality_report(pages: list[dict[str, Any]], game_index: list[dict[str, Any]]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    low_confidence: list[dict[str, Any]] = []
    page_summary: list[dict[str, Any]] = []
    for page in pages:
        confidence = page.get("confidence_scores") or {}
        average = confidence.get("average_page_confidence_score")
        words = confidence.get("word_confidence_scores") or []
        weak_words = [
            {"text": word.get("text", "").strip(), "confidence": word.get("confidence")}
            for word in words
            if isinstance(word.get("confidence"), (int, float))
            and word["confidence"] < 0.8
            and word.get("text", "").strip()
        ]
        if weak_words:
            low_confidence.append({"pdfPage": int(page["index"]) + 1, "words": weak_words})
        page_summary.append(
            {
                "pdfPage": int(page["index"]) + 1,
                "averageConfidence": average,
                "markdownCharacters": len(str(page.get("markdown", ""))),
                "images": len(page.get("images", [])),
                "weakWords": len(weak_words),
            }
        )
    report = {
        "status": "ocr-beta",
        "pages": len(pages),
        "games": len(game_index),
        "pageSummary": page_summary,
        "lowConfidence": low_confidence,
    }
    (REPORTS / "quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    averages = [item["averageConfidence"] for item in page_summary if isinstance(item["averageConfidence"], float)]
    report_md = [
        "# Raport jakości Mistral OCR",
        "",
        f"- Strony: {len(pages)}",
        f"- Gry: {len(game_index)}",
        f"- Średnia pewność stron: {sum(averages) / len(averages):.4f}" if averages else "- Średnia pewność: brak",
        f"- Strony zawierające słowa poniżej 0,80: {len(low_confidence)}",
        "",
        "Pełna lista słów i ocen znajduje się w `quality.json`.",
    ]
    (REPORTS / "README.md").write_text("\n".join(report_md) + "\n", encoding="utf-8")


def main() -> None:
    pages = load_pages()
    ASSETS.mkdir(parents=True, exist_ok=True)
    lines = build_lines(pages)
    games = make_games(lines)

    for generated_dir in [DOCS / "gry", DOCS / "wprowadzenie"]:
        if generated_dir.exists():
            shutil.rmtree(generated_dir)

    game_index = write_games(lines, games)
    write_intro_documents(lines, games)
    write_index(game_index)
    write_table_of_contents(game_index)
    write_about()
    write_llm_exports(game_index)
    write_quality_report(pages, game_index)
    (ROOT / "data" / "ocr" / "games.json").write_text(
        json.dumps(game_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(game_index)} game pages and supporting content")


if __name__ == "__main__":
    main()
