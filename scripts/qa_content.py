#!/usr/bin/env python3
"""Structural acceptance checks for the OCR corpus and generated site."""

from __future__ import annotations

import gzip
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from scripts.line_breaks import Line, classify_break
except ModuleNotFoundError:
    from line_breaks import Line, classify_break


ROOT = Path(__file__).resolve().parents[1]
POLONA_URL = "https://polona.pl/item-view/0782bd3a-4d20-41be-86f8-bcdfc65555c5?page=0"
BASE = "/harcerz-w-polu"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"a", "link"} and attributes.get("href"):
            self.links.append(str(attributes["href"]))
        if tag in {"img", "script", "source"} and attributes.get("src"):
            self.links.append(str(attributes["src"]))


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def remaining_high_confidence_breaks(content: str) -> list[tuple[str, str]]:
    if content.startswith("---\n"):
        _, _, content = content.partition("\n---\n")
    lines = content.splitlines()
    findings: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip():
            index += 1
            continue
        before_index = index - 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if before_index < 0 or index >= len(lines):
            continue
        decision = classify_break(Line(lines[before_index], 0), Line(lines[index], 0))
        if decision and decision.confidence == "high":
            findings.append((lines[before_index][-80:], lines[index][:80]))
    return findings


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    pages: dict[int, dict] = {}
    for path in sorted((ROOT / "data" / "ocr" / "chunks").glob("pages-*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            response = json.load(stream)
        for page in response.get("pages", []):
            index = int(page["index"])
            if index in pages:
                fail(f"Duplicate OCR page index {index}", errors)
            pages[index] = page
    if sorted(pages) != list(range(260)):
        fail("OCR coverage is not exactly page indexes 0-259", errors)

    manifest_path = ROOT / "data" / "ocr" / "manifest.json"
    if not manifest_path.exists():
        fail("Missing OCR manifest", errors)
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = manifest.get("source", {})
        if source.get("polonaUrl") != POLONA_URL:
            fail("Manifest is missing the exact Polona source URL", errors)
        if "Domena publiczna" not in source.get("rightsStatement", ""):
            fail("Manifest is missing the Polona public-domain statement", errors)
        if not manifest.get("upload", {}).get("deleted"):
            fail("Temporary Mistral upload was not deleted", errors)

    games_path = ROOT / "data" / "ocr" / "games.json"
    if not games_path.exists():
        fail("Missing generated games index", errors)
        games = []
    else:
        games = json.loads(games_path.read_text(encoding="utf-8"))
    numbers = [item.get("number") for item in games]
    if numbers != list(range(1, 118)):
        fail("Game index is not the exact sequence 1-117", errors)

    game_files = sorted(
        path
        for path in (ROOT / "src" / "content" / "docs" / "gry").glob("**/[0-9][0-9][0-9]-*.md")
        if not path.name.startswith("000-")
    )
    if len(game_files) != 117:
        fail(f"Expected 117 game Markdown files, found {len(game_files)}", errors)

    found_numbers: list[int] = []
    for path in game_files:
        content = path.read_text(encoding="utf-8")
        number_match = re.search(r"^number:\s*(\d+)\s*$", content, flags=re.M)
        if not number_match:
            fail(f"Missing number in {path.relative_to(ROOT)}", errors)
            continue
        number = int(number_match.group(1))
        found_numbers.append(number)
        if f"sourceUrl: \"{POLONA_URL}\"" not in content:
            fail(f"Missing Polona source URL in game {number}", errors)
        if "status: ocr-beta" not in content:
            fail(f"Missing beta status in game {number}", errors)
        if "pdfPages: []" in content:
            fail(f"Missing PDF page range in game {number}", errors)
        body = content.split("---", 2)[-1].strip()
        if len(body) < 120:
            fail(f"Game {number} body is unexpectedly short", errors)
        if re.search(r"\w-\n\w", body):
            warnings.append(f"Game {number} contains a possible line-break hyphenation")
        for asset in re.findall(r"/harcerz-w-polu/book/assets/([^)\s]+)", content):
            if not (ROOT / "public" / "book" / "assets" / asset).exists():
                fail(f"Missing referenced asset {asset} in game {number}", errors)

    if sorted(found_numbers) != list(range(1, 118)):
        fail("Markdown game numbers contain gaps or duplicates", errors)

    line_break_report_path = ROOT / "data" / "ocr" / "reports" / "line-breaks.json"
    if not line_break_report_path.exists():
        fail("Missing paragraph line-break report", errors)
    else:
        line_break_report = json.loads(line_break_report_path.read_text(encoding="utf-8"))
        entries = line_break_report.get("entries", [])
        summary = line_break_report.get("summary", {})
        auto_joined = sum(entry.get("action") == "auto-joined" for entry in entries)
        review = sum(entry.get("action") == "review" for entry in entries)
        if summary.get("detected") != len(entries):
            fail("Line-break report detected count does not match its entries", errors)
        if summary.get("autoJoined") != auto_joined or summary.get("review") != review:
            fail("Line-break report action totals are inconsistent", errors)
        if any(
            entry.get("confidence") == "high" and entry.get("action") != "auto-joined"
            for entry in entries
        ):
            fail("A high-confidence paragraph break was not automatically joined", errors)
        example = next(
            (
                entry
                for entry in entries
                if entry.get("document") == "gry/wiekszy-zespol/113-napad-na-linie-kolejowa"
                and entry.get("before", "").endswith("długości")
                and entry.get("after", "").startswith("drogi do liczby broniących")
            ),
            None,
        )
        if not example or example.get("action") != "auto-joined":
            fail("The verified game 113 page continuation was not automatically joined", errors)

    for path in sorted((ROOT / "src" / "content" / "docs").glob("**/*.md*")):
        content = path.read_text(encoding="utf-8")
        findings = remaining_high_confidence_breaks(content)
        if findings:
            before, after = findings[0]
            fail(
                f"Unresolved high-confidence paragraph break in {path.relative_to(ROOT)}: "
                f"{before!r} / {after!r}",
                errors,
            )

    required_pages = [
        ROOT / "src" / "content" / "docs" / "index.mdx",
        ROOT / "src" / "content" / "docs" / "spis-tresci.md",
        ROOT / "src" / "content" / "docs" / "o-wydaniu.md",
    ]
    for path in required_pages:
        if not path.exists():
            fail(f"Missing site page {path.relative_to(ROOT)}", errors)
            continue
        content = path.read_text(encoding="utf-8")
        if POLONA_URL not in content:
            fail(f"Missing Polona link in {path.relative_to(ROOT)}", errors)

    public_pdf = ROOT / "public" / "book" / "harcerz-w-polu.pdf"
    if not public_pdf.exists() or public_pdf.stat().st_size != 69_337_979:
        fail("Published PDF is missing or does not match the inspected source size", errors)

    cover = ROOT / "public" / "book" / "cover.png"
    if not cover.exists() or cover.stat().st_size < 500_000:
        fail("Published cover image is missing or unexpectedly small", errors)

    llm_files = [
        ROOT / "public" / "llms.txt",
        ROOT / "public" / "llms-full.txt",
        ROOT / "public" / "book" / "harcerz-w-polu.md",
        ROOT / "public" / "book" / "harcerz-w-polu.txt",
        ROOT / "public" / "book" / "games.json",
        ROOT / "public" / "robots.txt",
    ]
    for path in llm_files:
        if not path.exists():
            fail(f"Missing LLM-friendly export {path.relative_to(ROOT)}", errors)
            continue
        content = path.read_text(encoding="utf-8")
        if POLONA_URL not in content:
            fail(f"Missing Polona provenance in {path.relative_to(ROOT)}", errors)
    full_text = ROOT / "public" / "llms-full.txt"
    if full_text.exists() and full_text.stat().st_size < 300_000:
        fail("Full LLM text export is unexpectedly small", errors)

    dist = ROOT / "dist"
    if dist.exists():
        html_files = sorted(dist.glob("**/*.html"))
        if len(html_files) != 130:
            fail(f"Expected 130 generated HTML pages, found {len(html_files)}", errors)
        if not (dist / "pagefind" / "pagefind.js").exists():
            fail("Pagefind search index is missing", errors)
        for html_file in html_files:
            parser = LinkParser()
            parser.feed(html_file.read_text(encoding="utf-8"))
            for link in parser.links:
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path.startswith(BASE):
                    continue
                relative = unquote(parsed.path[len(BASE) :]).lstrip("/")
                if not relative:
                    target = dist / "index.html"
                else:
                    target = dist / relative
                    if parsed.path.endswith("/"):
                        target = target / "index.html"
                if not target.exists():
                    fail(
                        f"Broken built link from {html_file.relative_to(dist)} to {parsed.path}",
                        errors,
                    )

    secret_pattern = re.compile(r"MISTRAL_API_KEY\s*=\s*\S+")
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {"node_modules", ".git", "dist"} for part in path.parts):
            continue
        if path.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png", ".gz"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in secret_pattern.finditer(content):
            if "os.environ" not in match.group(0) and "[hidden]" not in match.group(0):
                fail(f"Possible Mistral API key assignment in {path.relative_to(ROOT)}", errors)

    print(f"OCR pages: {len(pages)}/260")
    print(f"Game pages: {len(game_files)}/117")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings[:20]:
        print(f"warning: {warning}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print("All structural checks passed")


if __name__ == "__main__":
    main()
