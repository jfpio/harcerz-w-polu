#!/usr/bin/env python3
"""Classify and repair paragraph breaks introduced by OCR or page boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


LOWERCASE_START = re.compile(r"[a-ząćęłńóśźż]")
NON_PROSE_BLOCKS = {"header", "footer", "image", "table", "title"}
TERMINAL_PUNCTUATION = ".!?…"
OPENING_MARKS = " \t*_`'\"„“«["
CLOSING_MARKS = " \t*_`'\"”’»)]}"


@dataclass(frozen=True)
class Line:
    text: str
    pdf_page: int
    block_type: str | None = None
    top: int | None = None
    bottom: int | None = None
    page_height: int | None = None


@dataclass(frozen=True)
class BreakDecision:
    rule: str
    confidence: str
    action: str
    join_without_space: bool = False
    drop_after_prefix: int = 0


def markdown_kind(line: Line) -> str:
    text = line.text.strip()
    if not text:
        return "blank"
    if line.block_type in NON_PROSE_BLOCKS:
        return str(line.block_type)
    if re.match(r"^#{1,6}\s+", text):
        return "heading"
    if re.match(r"^(?:[-+*]|\d+[.)]|[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż][.)])\s+", text):
        return "list"
    if re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", text):
        return "diagram-label"
    if text.startswith((">", "```", "~~~", "|", "![", "<")):
        return "markup"
    if re.match(r"^(?:-{3,}|\*{3,}|_{3,})$", text):
        return "separator"
    if re.match(r"^\[\^[^]]+\]:", text):
        return "footnote"
    return "prose"


def first_meaningful_character(text: str) -> str:
    value = text.lstrip(OPENING_MARKS)
    return value[0] if value else ""


def ends_sentence(text: str) -> bool:
    value = text.rstrip(CLOSING_MARKS)
    return bool(value) and value[-1] in TERMINAL_PUNCTUATION


def classify_break(before: Line, after: Line) -> BreakDecision | None:
    if markdown_kind(before) != "prose" or markdown_kind(after) != "prose":
        return None

    first = first_meaningful_character(after.text)
    starts_lowercase = bool(first and LOWERCASE_START.fullmatch(first))
    starts_parenthesis = after.text.lstrip().startswith("(")
    page_boundary = before.pdf_page != after.pdf_page
    boundary_label = "page-boundary" if page_boundary else "ocr-block"

    before_words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", before.text)
    after_words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", after.text)
    if before_words and after_words:
        previous_word = before_words[-1].lower()
        next_word = after_words[0].lower()
        if 3 <= len(next_word) < len(previous_word) and previous_word.endswith(next_word):
            return BreakDecision(
                rule=f"{boundary_label}-duplicate-word-fragment",
                confidence="high",
                action="auto-joined",
                drop_after_prefix=len(after_words[0]),
            )

    if before.text.rstrip().endswith("-") and starts_lowercase:
        return BreakDecision(
            rule=f"{boundary_label}-hyphenated-word",
            confidence="high",
            action="auto-joined",
            join_without_space=True,
        )

    if page_boundary and before.text.rstrip().endswith(("—", "–")):
        return BreakDecision(
            rule="page-boundary-continuation-dash",
            confidence="high",
            action="auto-joined",
        )

    if not ends_sentence(before.text) and (starts_lowercase or starts_parenthesis):
        continuation = "lowercase" if starts_lowercase else "parenthesis"
        return BreakDecision(
            rule=f"{boundary_label}-{continuation}",
            confidence="high",
            action="auto-joined",
        )

    if not ends_sentence(before.text):
        return BreakDecision(
            rule=f"{boundary_label}-nonterminal-uppercase",
            confidence="medium",
            action="review",
        )

    return None


def _snippet(text: str, *, from_end: bool) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 140:
        return compact
    return ("…" + compact[-139:]) if from_end else (compact[:139] + "…")


def _position(line: Line) -> dict[str, Any]:
    return {
        "pdfPage": line.pdf_page,
        "printedPage": line.pdf_page - 6 if line.pdf_page > 6 else None,
        "blockType": line.block_type,
        "top": line.top,
        "bottom": line.bottom,
        "pageHeight": line.page_height,
    }


def clean_lines(
    lines: Iterable[Line],
    *,
    document: str,
    report: list[dict[str, Any]],
    drop_first_heading: bool = False,
) -> str:
    values = list(lines)
    while values and not values[0].text.strip():
        values.pop(0)
    while values and not values[-1].text.strip():
        values.pop()
    if drop_first_heading and values:
        values.pop(0)
        while values and not values[0].text.strip():
            values.pop(0)

    output: list[str] = []
    index = 0
    while index < len(values):
        current = values[index]
        if current.text.strip():
            output.append(current.text)
            index += 1
            continue

        blank_start = index
        while index < len(values) and not values[index].text.strip():
            index += 1
        if not output or index >= len(values):
            continue

        before_index = blank_start - 1
        while before_index >= 0 and not values[before_index].text.strip():
            before_index -= 1
        before = values[before_index]
        after = values[index]
        decision = classify_break(before, after)
        if decision is None:
            output.append("")
            continue

        entry = {
            "document": document,
            "pdfPages": sorted({before.pdf_page, after.pdf_page}),
            "printedPages": sorted(
                {page - 6 for page in (before.pdf_page, after.pdf_page) if page > 6}
            ),
            "rule": decision.rule,
            "confidence": decision.confidence,
            "action": decision.action,
            "before": _snippet(before.text, from_end=True),
            "after": _snippet(after.text, from_end=False),
            "positions": {
                "before": _position(before),
                "after": _position(after),
            },
        }
        report.append(entry)

        if decision.action == "auto-joined":
            if decision.drop_after_prefix:
                remainder = after.text.lstrip()[decision.drop_after_prefix :].lstrip()
                output[-1] = output[-1].rstrip() + ((" " + remainder) if remainder else "")
            elif decision.join_without_space:
                output[-1] = output[-1].rstrip()[:-1] + after.text.lstrip()
            else:
                output[-1] = output[-1].rstrip() + " " + after.text.lstrip()
            index += 1
        else:
            output.append("")

    text = "\n".join(output).strip()
    text = re.sub(r"(?<=\w)-\n(?=[a-ząćęłńóśźż])", "", text)
    return re.sub(r"\n{3,}", "\n\n", text)
