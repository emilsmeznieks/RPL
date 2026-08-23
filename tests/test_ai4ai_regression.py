import json
from pathlib import Path
import unittest

from rpl.digest import build_digest
from rpl.models import Digest, Paper, Section, SourcedStatement
from rpl.parser import parse_arxiv_html
from rpl.quality import apply_output_quality_rules
from rpl.render import knowledge_payload, render_html, render_markdown
from rpl.visual import build_scoring_spec, build_visual_spec


FIXTURE = Path(__file__).parent / "fixtures" / "ai4ai_bench_regression.html"
TABLE_DUMP = "System Harness Effort OpenR1"
RAW_READER_TOKENS = (r"\uparrow", r"\downarrow", r"\ast", r"\perp", r"\infty")


class AI4AIBenchRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paper = parse_arxiv_html(
            FIXTURE.read_text(encoding="utf-8"),
            "https://arxiv.org/html/2608.20318",
        )
        cls.digest = build_digest(cls.paper)
        cls.visual = build_visual_spec(cls.paper)
        cls.refined, cls.quality = apply_output_quality_rules(
            cls.paper, cls.digest, cls.visual, []
        )
        cls.markdown = render_markdown(cls.paper, cls.refined, cls.quality)
        cls.html = render_html(cls.paper, cls.refined, output_quality=cls.quality)
        cls.payload = knowledge_payload(cls.paper, cls.refined, output_quality=cls.quality)

    def test_table_paragraphs_never_become_paper_prose(self) -> None:
        prose = " ".join(
            paragraph
            for section in self.paper.sections
            for paragraph in section.paragraphs
        )

        self.assertNotIn(TABLE_DUMP, prose)
        self.assertNotIn(TABLE_DUMP, self.markdown)
        reader_html = self.html.split(
            '<section class="card wide" aria-labelledby="agent-data">', 1
        )[0]
        self.assertNotIn(TABLE_DUMP, reader_html)
        self.assertTrue(
            any("paragraph-like elements" in warning for warning in self.paper.extraction_warnings)
        )

    def test_front_matter_and_missing_source_figures_are_retained(self) -> None:
        front = self.paper.sections[0]
        all_figures = [
            record for section in self.paper.sections for record in section.figure_records
        ]

        self.assertEqual(front.title, "Front matter")
        self.assertEqual(front.figure_records[0].anchor, "S0.F1")
        self.assertIn("lifecycle every task runs through", front.figures[0])
        self.assertEqual(len(all_figures), 3)
        self.assertTrue(all(record.image_status == "unavailable" for record in all_figures))
        self.assertEqual(self.payload["provenance"]["source_images"]["unavailable"], 3)
        self.assertIn("Figures from the paper", self.html)
        self.assertIn("Figure 2:", self.html)
        self.assertIn("Figure 3:", self.html)
        self.assertNotIn("<img ", self.html)

    def test_piecewise_equation_and_scoring_visual_are_preserved(self) -> None:
        scoring_section = next(
            section for section in self.paper.sections if section.title == "Scoring"
        )
        scoring = build_scoring_spec(self.paper)

        self.assertTrue(any(r"\begin{cases}" in equation for equation in scoring_section.equations))
        self.assertIn("S2.E1.m1", scoring_section.equation_anchors)
        self.assertIsNotNone(scoring)
        self.assertEqual([level.value for level in scoring.levels], ["0", "0.1", "1.0"])
        self.assertIn("separate linear branches", scoring.explanation)
        self.assertIn("score-ladder", self.html)
        self.assertIn(r"\begin{cases}", self.payload["scoring"]["equation"])

    def test_selects_the_benchmark_lifecycle_instead_of_an_outline(self) -> None:
        self.assertEqual(self.visual.visual_type, "benchmark-process")
        self.assertEqual(self.visual.confidence, "high")
        self.assertEqual(
            [node.label for node in self.visual.nodes],
            [
                "Frozen repository, starting model, and proxy metric",
                "Four-hour agent exploration on one B300",
                "Source-code patch only",
                "Fresh container and clean-start execution",
                "Up to twelve-hour verification or training",
                "Fixed evaluator hidden from the agent",
                "Normalized final score",
            ],
        )
        self.assertTrue(all(node.source_text for node in self.visual.nodes))
        self.assertNotIn(
            '<ol class="visual-flow" data-visual-type="paper-outline">', self.html
        )
        self.assertNotIn('<h2 id="map">Paper map</h2>', self.html)

    def test_visualizes_execution_and_learning_change_layers(self) -> None:
        change_layers = self.payload["change_layers"]

        self.assertEqual(change_layers["visual_type"], "change-layers")
        self.assertEqual(
            [node["group"] for node in change_layers["nodes"]],
            ["execution"] * 4 + ["learning"] * 4,
        )
        self.assertIn("Execution-level changes", self.html)
        self.assertIn("Learning-level changes", self.html)
        self.assertNotIn("neural-network architecture", self.html.lower())

    def test_reader_shows_concise_quantitative_findings(self) -> None:
        evidence = " ".join(item.text for item in self.refined.evidence)
        for value in ("0.166", "0.250", "0.288", "0.226", "0.126", "8\\%", "64\\%", "0.094", "0.196"):
            self.assertIn(value, evidence)
        self.assertTrue(all(len(item.text) <= 700 for item in self.refined.evidence))

    def test_reader_prose_has_no_raw_latex_control_tokens(self) -> None:
        reader_html = self.html.split(
            '<section class="card wide" aria-labelledby="agent-data">', 1
        )[0]
        for token in RAW_READER_TOKENS:
            self.assertNotIn(token, self.markdown)
            self.assertNotIn(token, reader_html)

    def test_json_is_valid_sourced_and_not_marked_ready(self) -> None:
        decoded = json.loads(json.dumps(self.payload))

        self.assertEqual(decoded["output_quality"]["status"], "partial")
        self.assertTrue(
            any("No explicit limitations" in warning for warning in decoded["output_quality"]["warnings"])
        )
        self.assertTrue(
            any("unavailable" in warning for warning in decoded["output_quality"]["warnings"])
        )
        self.assertTrue(all(item["section"] for item in decoded["digest"]["evidence"]))
        self.assertTrue(all(node["source_text"] for node in decoded["visual"]["nodes"]))
        self.assertFalse(decoded["provenance"]["generated_claims"])

    def test_quality_filter_rejects_a_flattened_table_as_second_defense(self) -> None:
        table_dump = (
            "System Harness Effort Model Score Baseline Cost "
            + " ".join(f"Model-{index} {index / 100:.2f} {index}" for index in range(30))
        )
        digest = Digest(
            problem=SourcedStatement("Existing methods cannot solve the stated problem.", "Introduction"),
            core_idea=SourcedStatement("We introduce a benchmark for this problem.", "Abstract"),
            evidence=[SourcedStatement(table_dump, "Results")],
            limitations=[],
            takeaways=[],
            paper_type="empirical",
        )
        paper = Paper(
            "fixture",
            "Table defense",
            [],
            None,
            "https://arxiv.org/html/2608.20318",
            "We introduce a benchmark for this problem.",
            sections=[Section("Results", 2)],
        )

        refined, quality = apply_output_quality_rules(
            paper, digest, build_visual_spec(paper), []
        )

        self.assertEqual(refined.evidence, [])
        self.assertEqual(quality.status, "partial")
        self.assertTrue(
            any(
                "table-like evidence" in warning or "excessively long evidence" in warning
                for warning in quality.warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
