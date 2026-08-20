import unittest

from rpl.language import build_glossary, reading_text
from rpl.models import Paper, Section


class LanguageTests(unittest.TestCase):
    def test_removes_only_mechanical_reading_clutter(self) -> None:
        source = (
            r"The method improved accuracy [ 12, 19 ] by 8\% with a 2\times speedup "
            r"(\Delta=0.08, p_{\mathrm{Holm}}=0.04)."
        )

        result = reading_text(source)

        self.assertEqual(
            result,
            "The method improved accuracy by 8% with a 2× speedup (Δ=0.08, p (Holm)=0.04).",
        )

    def test_extracts_only_terms_defined_by_the_paper(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Definitions",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="Enterprise Resource Planning (ERP) records transactions.",
            sections=[
                Section(
                    "Method",
                    2,
                    anchor="S2",
                    paragraphs=[
                        "The large-language-model (LLM) agent chooses a tool. "
                        "An undefined short form (BAD) is ignored."
                    ],
                    paragraph_anchors=["S2.p1"],
                )
            ],
        )

        terms = build_glossary(paper)

        self.assertEqual(
            [(term.short_form, term.term) for term in terms],
            [("ERP", "Enterprise Resource Planning"), ("LLM", "large-language-model")],
        )
        self.assertEqual(terms[1].source_anchor, "S2.p1")

    def test_ignores_publication_names_as_glossary_terms(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Publication abbreviation",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/1706.03762",
            abstract="Results use the Wall Street Journal (WSJ) dataset.",
            sections=[Section("Introduction", 2)],
        )

        self.assertEqual(build_glossary(paper), [])


if __name__ == "__main__":
    unittest.main()
