#!/usr/bin/env python3
"""Regression tests for OCR paragraph-boundary cleanup."""

from __future__ import annotations

import unittest

from scripts.line_breaks import Line, clean_lines


class LineBreakTests(unittest.TestCase):
    def clean(
        self,
        before: str,
        after: str,
        *,
        before_page: int = 10,
        after_page: int = 11,
        before_type: str | None = "text",
        after_type: str | None = "text",
    ) -> tuple[str, list[dict]]:
        report: list[dict] = []
        result = clean_lines(
            [
                Line(before, before_page, block_type=before_type),
                Line("", before_page),
                Line(after, after_page, block_type=after_type),
            ],
            document="test",
            report=report,
        )
        return result, report

    def test_lowercase_page_continuation_is_joined(self) -> None:
        text, report = self.clean("przy dostosowaniu długości", "drogi do liczby broniących.")
        self.assertEqual(text, "przy dostosowaniu długości drogi do liczby broniących.")
        self.assertEqual(report[0]["action"], "auto-joined")

    def test_parenthetical_continuation_is_joined(self) -> None:
        text, report = self.clean("pozostać przez 5", "(ew. 5—8) minut.")
        self.assertEqual(text, "pozostać przez 5 (ew. 5—8) minut.")
        self.assertEqual(report[0]["confidence"], "high")

    def test_hyphenated_word_is_joined_without_space(self) -> None:
        text, report = self.clean("prze-", "rwany wyraz.")
        self.assertEqual(text, "przerwany wyraz.")
        self.assertTrue(report[0]["rule"].endswith("hyphenated-word"))

    def test_page_continuation_after_dash_is_joined(self) -> None:
        text, report = self.clean("podaj znak itp. —", "Po krótkim czasie harcerze się nauczą.")
        self.assertEqual(text, "podaj znak itp. — Po krótkim czasie harcerze się nauczą.")
        self.assertEqual(report[0]["rule"], "page-boundary-continuation-dash")

    def test_complete_paragraph_is_preserved(self) -> None:
        text, report = self.clean("Pierwszy akapit.", "Drugi akapit.")
        self.assertEqual(text, "Pierwszy akapit.\n\nDrugi akapit.")
        self.assertEqual(report, [])

    def test_heading_is_not_joined(self) -> None:
        text, report = self.clean("Tekst bez kropki", "## Nowy dział", after_type="title")
        self.assertEqual(text, "Tekst bez kropki\n\n## Nowy dział")
        self.assertEqual(report, [])

    def test_list_is_not_joined(self) -> None:
        text, report = self.clean("Wprowadzenie bez kropki", "- pierwszy punkt")
        self.assertEqual(text, "Wprowadzenie bez kropki\n\n- pierwszy punkt")
        self.assertEqual(report, [])

    def test_lettered_list_is_not_joined(self) -> None:
        text, report = self.clean("Przykłady:", "a) Pierwszy przykład")
        self.assertEqual(text, "Przykłady:\n\na) Pierwszy przykład")
        self.assertEqual(report, [])

    def test_image_is_not_joined(self) -> None:
        text, report = self.clean("Podpis bez kropki", "![Mapa](mapa.png)", after_type="image")
        self.assertEqual(text, "Podpis bez kropki\n\n![Mapa](mapa.png)")
        self.assertEqual(report, [])

    def test_diagram_labels_are_not_joined(self) -> None:
        text, report = self.clean("M", "m")
        self.assertEqual(text, "M\n\nm")
        self.assertEqual(report, [])

    def test_duplicate_word_fragment_is_removed(self) -> None:
        text, report = self.clean("przedmiotów, których", "rych miejsce należy ustalić")
        self.assertEqual(text, "przedmiotów, których miejsce należy ustalić")
        self.assertEqual(report[0]["action"], "auto-joined")
        self.assertTrue(report[0]["rule"].endswith("duplicate-word-fragment"))

    def test_uncertain_uppercase_continuation_is_reported_only(self) -> None:
        text, report = self.clean("Tekst bez kropki", "Możliwa kontynuacja")
        self.assertEqual(text, "Tekst bez kropki\n\nMożliwa kontynuacja")
        self.assertEqual(report[0]["action"], "review")
        self.assertEqual(report[0]["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
