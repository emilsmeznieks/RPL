from pathlib import Path
import re
import unittest

from rpl.digest import build_digest
from rpl.parser import parse_arxiv_html
from rpl.models import Digest, Paper, Section, SourcedStatement
from rpl.render import knowledge_payload, render_html, render_markdown


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class DigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paper = parse_arxiv_html(
            FIXTURE.read_text(encoding="utf-8"),
            "https://arxiv.org/html/2607.17331v1",
        )
        cls.digest = build_digest(cls.paper)

    def test_extracts_problem_and_core_idea(self) -> None:
        self.assertIsNotNone(self.digest.problem)
        self.assertIsNotNone(self.digest.core_idea)
        self.assertEqual(self.digest.problem.section, "Introduction")
        self.assertIn("role-aligned", self.digest.core_idea.text)
        self.assertEqual(self.digest.paper_type, "empirical")
        self.assertEqual(self.digest.paper_type_confidence, "moderate")

    def test_problem_selection_prefers_the_explicit_constraint_over_background(self) -> None:
        paper = Paper(
            paper_id="1706.03762",
            title="Attention Is All You Need",
            authors=[],
            published="2017",
            source_url="https://arxiv.org/html/1706.03762",
            abstract=(
                "The dominant sequence transduction models use recurrent or convolutional networks. "
                "We propose the Transformer based solely on attention mechanisms."
            ),
            sections=[
                Section(
                    "Introduction",
                    2,
                    anchor="S1",
                    paragraphs=[
                        "Recurrent neural networks are established approaches for sequence modeling.",
                        "This inherently sequential nature precludes parallelization within training examples, which becomes critical at longer sequence lengths as memory constraints limit batching.",
                        "Recent work improved efficiency, but the fundamental constraint of sequential computation remains.",
                    ],
                    paragraph_anchors=["S1.p1", "S1.p2", "S1.p3"],
                )
            ],
        )

        digest = build_digest(paper)

        self.assertIsNotNone(digest.problem)
        self.assertIn("precludes parallelization", digest.problem.text)
        self.assertEqual(digest.problem.source_anchor, "S1.p2")

    def test_problem_selection_does_not_use_background_as_a_fallback(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Background only",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="Existing systems have been widely used across many applications.",
            sections=[Section("Introduction", 2)],
        )

        self.assertIsNone(build_digest(paper).problem)

    def test_keeps_evidence_and_limitations_sourced(self) -> None:
        self.assertGreaterEqual(len(self.digest.evidence), 2)
        self.assertTrue(all(item.section for item in self.digest.evidence))
        self.assertGreaterEqual(len(self.digest.limitations), 2)
        self.assertTrue(any("synthetic" in item.text.lower() for item in self.digest.limitations))

    def test_selects_only_one_claim_from_each_exact_source_paragraph(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Paragraph deduplication",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="This paper presents an evaluated method for a difficult problem.",
            sections=[
                Section(
                    "Results",
                    2,
                    anchor="S3",
                    paragraphs=[
                        "The system achieved 90% accuracy across 100 trials. "
                        "It also increased completion to 95% over 120 trials.",
                        "The baseline reached 80% accuracy across 100 trials.",
                    ],
                    paragraph_anchors=["S3.p1", "S3.p2"],
                )
            ],
        )

        evidence = build_digest(paper).evidence

        self.assertEqual(
            [item.source_anchor for item in evidence], ["S3.p1", "S3.p2"]
        )

    def test_takeaways_prefer_substance_over_transition_text(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Takeaway selection",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="This paper presents a tested architecture for a difficult problem.",
            sections=[
                Section(
                    "Discussion",
                    2,
                    paragraphs=[
                        "The evidence assembled across experiments supports three principal findings. "
                        "The architecture reduced tool-selection error in the reported evaluation and preserved backend constraints."
                    ],
                ),
                Section(
                    "Conclusion",
                    2,
                    paragraphs=[
                        "The study reports that role-aligned agents completed the tested workflows under human oversight."
                    ],
                ),
            ],
        )

        takeaways = build_digest(paper).takeaways

        self.assertIn("role-aligned agents", takeaways[0].text)
        self.assertFalse(any("supports three principal findings" in item.text for item in takeaways))

    def test_renders_human_and_agent_outputs(self) -> None:
        markdown = render_markdown(self.paper, self.digest)
        payload = knowledge_payload(self.paper, self.digest)
        self.assertIn("## The core idea", markdown)
        self.assertIn("```mermaid", markdown)
        self.assertFalse(payload["provenance"]["generated_claims"])
        self.assertEqual(payload["schema_version"], "0.10")
        self.assertEqual(payload["output_quality"]["status"], "ready")
        self.assertEqual(payload["comparison"]["schema_version"], "0.2")
        self.assertEqual(payload["comparison"]["status"], "not-generated")
        self.assertEqual(
            payload["comparison"]["focal_paper_id"], self.paper.paper_id
        )
        self.assertEqual(payload["visual"]["visual_type"], "process")
        self.assertEqual(payload["visual"]["nodes"][0]["label"], "Plan")
        self.assertEqual(payload["visual"]["nodes"][0]["source_anchor"], "S2.p1")
        self.assertIn("Results reported in the paper", markdown)
        self.assertIn("https://arxiv.org/html/2607.17331v1#S3.p1", markdown)
        self.assertEqual(payload["digest"]["evidence"][0]["source_anchor"], "S3.p1")

    def test_extracts_results_from_a_theoretical_paper(self) -> None:
        paper = Paper(
            paper_id="hep-th/9901001",
            title="A theoretical paper",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/hep-th/9901001",
            abstract=(
                "We explicitly give the correspondence between two invariant spectra."
            ),
            sections=[
                Section(
                    "Spectrum and Correspondence",
                    2,
                    paragraphs=[
                        "Definitions used by the formalism are introduced here.",
                        "Can we establish a different correspondence from these assumptions?",
                    ],
                    equations=["x = y", "y = z", "z = x"],
                    paragraph_anchors=["S2.p1", "S2.p2"],
                ),
                Section(
                    "Conclusion",
                    2,
                    anchor="S4",
                    paragraphs=[
                        "We establish the correspondence between the two invariant charge systems."
                    ],
                    paragraph_anchors=["S4.p1"],
                ),
            ],
        )

        digest = build_digest(paper)
        markdown = render_markdown(paper, digest)

        self.assertEqual(digest.paper_type, "theoretical")
        self.assertEqual(digest.paper_type_confidence, "moderate")
        self.assertIsNone(digest.problem)
        self.assertIn("correspondence", digest.core_idea.text.lower())
        self.assertEqual(digest.evidence[0].source_anchor, "S4.p1")
        self.assertFalse(any("?" in item.text for item in digest.evidence))
        self.assertNotIn(digest.core_idea.text, [item.text for item in digest.evidence])
        self.assertFalse(
            {item.text for item in digest.evidence}
            & {item.text for item in digest.takeaways}
        )
        self.assertEqual(digest.takeaways, [])
        self.assertIn("## Main theoretical results stated in the paper", markdown)

    def test_keeps_ambiguous_paper_type_unknown(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="An ambiguous paper",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="We describe a method for organizing a collection of records.",
            sections=[Section("Introduction", 2), Section("Method", 2)],
        )

        digest = build_digest(paper)

        self.assertEqual(digest.paper_type, "unknown")
        self.assertEqual(digest.paper_type_confidence, "low")

    def test_html_is_standalone_and_escapes_paper_content(self) -> None:
        malicious_paper = Paper(
            paper_id="test-paper",
            title='<script>alert("title")</script>',
            authors=['A & B'],
            published=None,
            source_url='javascript:alert("link")',
            abstract='<img src=x onerror=alert("abstract")>',
            sections=[Section(title="Method <unsafe>", level=2)],
        )
        malicious_digest = Digest(
            problem=SourcedStatement('<script>alert("problem")</script>', "Abstract"),
            core_idea=None,
            evidence=[],
            limitations=[],
            takeaways=[],
        )

        html = render_html(malicious_paper, malicious_digest)

        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("Content-Security-Policy", html)
        self.assertEqual(html.count("<script>"), 0)
        self.assertNotIn("<script>alert", html.lower())
        self.assertNotIn('href="javascript:', html.lower())
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Method &lt;unsafe&gt;", html)
        self.assertIn('href="#"', html)
        self.assertNotIn("https://cdn", html)

    def test_html_is_script_free_and_links_sources(self) -> None:
        html = render_html(self.paper, self.digest)
        policy = re.search(r'Content-Security-Policy" content="([^"]+)', html)

        self.assertIsNotNone(policy)
        self.assertNotIn("script-src", policy.group(1))
        self.assertNotIn("<script", html)
        self.assertNotIn("data-action=", html)
        self.assertIn("prefers-reduced-motion:reduce", html)
        self.assertIn(
            'href="https://arxiv.org/html/2607.17331v1#S3.p1"',
            html,
        )
        self.assertEqual(html.count('class="source-label visual-source"'), 1)
        self.assertIn(
            'href="https://arxiv.org/html/2607.17331v1#S2.p1"',
            html,
        )

    def test_html_uses_native_reading_and_accessibility_foundations(self) -> None:
        html = render_html(self.paper, self.digest)

        self.assertIn('-apple-system,BlinkMacSystemFont,"SF Pro Text"', html)
        self.assertIn("@media (prefers-contrast:more)", html)
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertNotIn("RPL paper classification", html)
        self.assertNotIn("RPL · Research paper guide", html)
        self.assertNotIn('class="confidence', html.lower())
        self.assertNotIn("moderate confidence", html.lower())
        self.assertNotIn("visual-pulse", html)

    def test_outline_is_compact_and_does_not_duplicate_the_paper_map(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Outline fallback",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="A complete abstract without an explicit process or architecture.",
            sections=[
                Section("Introduction", 2, anchor="S1"),
                Section("Results", 2, anchor="S2"),
            ],
        )

        html = render_html(paper, build_digest(paper))

        self.assertEqual(html.count("Paper map"), 0)
        self.assertIn('data-visual-type="paper-outline"', html)
        self.assertNotIn('class="source-label visual-source"', html)
        self.assertIn('align-items:start', html)

    def test_older_section_data_falls_back_to_the_section_anchor(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Compatible input",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="This paper presents a useful approach to a difficult problem.",
            sections=[
                Section(
                    "Results",
                    2,
                    anchor="S3",
                    paragraphs=[
                        "The method achieved 90% accuracy across 100 trials.",
                        "The baseline reached 80% accuracy across 100 trials.",
                    ],
                )
            ],
        )

        evidence = build_digest(paper).evidence

        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(item.source_anchor == "S3" for item in evidence))

    def test_generated_reader_copy_is_neutral(self) -> None:
        html = render_html(self.paper, self.digest).lower()

        self.assertIn("results reported in the paper", html)
        for unsupported_phrase in (
            "groundbreaking",
            "revolutionary",
            "this proves",
            "obviously",
            "undeniably",
        ):
            self.assertNotIn(unsupported_phrase, html)


if __name__ == "__main__":
    unittest.main()
