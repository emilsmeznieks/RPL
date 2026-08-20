import unittest

from rpl.models import Digest, Paper, Section, SourcedStatement
from rpl.quality import apply_output_quality_rules
from rpl.render import render_html
from rpl.visual import build_visual_spec


def statement(text: str, section: str) -> SourcedStatement:
    return SourcedStatement(text=text, section=section)


class OutputQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paper = Paper(
            paper_id="1706.03762",
            title="Attention Is All You Need",
            authors=["A. Researcher"],
            published="2017",
            source_url="https://arxiv.org/html/1706.03762",
            abstract="We propose the Transformer for sequence transduction tasks.",
            sections=[
                Section("Introduction", 2, anchor="S1"),
                Section("Training Data and Batching", 3, anchor="S5.SS1"),
                Section("Machine Translation", 3, anchor="S6.SS1"),
                Section("English Constituency Parsing", 3, anchor="S6.SS3"),
            ],
        )

    def test_keeps_results_and_removes_background_or_setup_statements(self) -> None:
        digest = Digest(
            problem=statement("Recurrent models limit parallel processing.", "Introduction"),
            core_idea=statement(
                "We propose the Transformer based solely on attention.", "Abstract"
            ),
            evidence=[
                statement(
                    "Recent work achieved significant improvements in computational efficiency [12].",
                    "Introduction",
                ),
                statement(
                    "We used a dataset consisting of 36M sentences and a 32000 word vocabulary.",
                    "Training Data and Batching",
                ),
                statement(
                    "The big Transformer outperforms prior models by more than 2.0 BLEU and achieves 28.4 BLEU.",
                    "Machine Translation",
                ),
                statement(
                    "The model achieves a BLEU score of 41.0 at less than one quarter of the previous training cost.",
                    "Machine Translation",
                ),
                statement(
                    "During inference, we increased the maximum output length to input length plus 300.",
                    "English Constituency Parsing",
                ),
            ],
            limitations=[],
            takeaways=[],
            paper_type="empirical",
        )

        refined, quality = apply_output_quality_rules(
            self.paper, digest, build_visual_spec(self.paper), []
        )

        self.assertEqual(len(refined.evidence), 2)
        self.assertTrue(all("BLEU" in item.text for item in refined.evidence))
        self.assertEqual(
            quality.warnings,
            ["Removed 3 low-signal result candidates from the reader output."],
        )

    def test_html_omits_empty_sections_and_expands_the_remaining_card(self) -> None:
        digest = Digest(
            problem=None,
            core_idea=statement(
                "We propose the Transformer based solely on attention.", "Abstract"
            ),
            evidence=[],
            limitations=[],
            takeaways=[],
        )

        html = render_html(self.paper, digest)

        self.assertNotIn('<h2 id="problem">', html)
        self.assertNotIn('<h2 id="evidence">', html)
        self.assertNotIn('<h2 id="limits">', html)
        self.assertIn(
            '<section class="card wide" aria-labelledby="idea">', html
        )
        self.assertIn('grid-auto-flow:row dense', html)


if __name__ == "__main__":
    unittest.main()
