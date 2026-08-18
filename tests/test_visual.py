import unittest

from rpl.models import Paper, Section, VisualEdge, VisualNode, VisualSpec
from rpl.parser import parse_arxiv_html
from rpl.visual import VisualSpecError, build_visual_spec, validate_visual_spec


class VisualSpecTests(unittest.TestCase):
    def test_extracts_layers_from_an_architecture_figure(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Layered architecture",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="We present a layered architecture for a difficult research problem.",
            sections=[Section(
                "System Architecture",
                2,
                figures=[
                    "Figure 1: The four-layer architecture separates concerns: "
                    "User Interface handles requests, Orchestration manages routing, "
                    "the Agent Layer provides expertise, and the ERP Backend ensures integrity."
                ],
            )],
        )

        visual = build_visual_spec(paper)

        self.assertEqual(visual.visual_type, "layered-architecture")
        self.assertEqual(
            [node.label for node in visual.nodes],
            ["User Interface", "Orchestration", "Agent Layer", "ERP Backend"],
        )
        self.assertTrue(all(node.source_text.startswith("Figure 1") for node in visual.nodes))

    def test_extracts_a_sourced_process_sequence(self) -> None:
        html = """
        <meta name="citation_title" content="A process paper">
        <div class="ltx_abstract"><p>We propose a useful process for a difficult research problem.</p></div>
        <h2>Method</h2>
        <p>Requests pass through plan, execute, reflect, and respond stages.</p>
        """
        paper = parse_arxiv_html(html, "https://arxiv.org/html/2607.10000v1")

        visual = build_visual_spec(paper)

        self.assertEqual(visual.visual_type, "process")
        self.assertEqual([node.label for node in visual.nodes], ["Plan", "Execute", "Reflect", "Respond"])
        self.assertTrue(all(node.source_section == "Method" for node in visual.nodes))
        self.assertEqual([(edge.source, edge.target) for edge in visual.edges], [
            ("step-1", "step-2"),
            ("step-2", "step-3"),
            ("step-3", "step-4"),
        ])

    def test_falls_back_to_an_explicit_low_confidence_outline(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="No process",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="An abstract long enough for the test.",
            sections=[Section("Introduction", 2), Section("Results", 2)],
        )

        visual = build_visual_spec(paper)

        self.assertEqual(visual.visual_type, "paper-outline")
        self.assertEqual(visual.confidence, "low")
        self.assertEqual([node.label for node in visual.nodes], ["Introduction", "Results"])

    def test_outline_supports_papers_without_level_two_headings(self) -> None:
        paper = Paper(
            paper_id="paper",
            title="Nested paper",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/2607.10000v1",
            abstract="An abstract long enough for the test.",
            sections=[Section("Nested introduction", 3)],
        )

        visual = build_visual_spec(paper)

        self.assertEqual([node.label for node in visual.nodes], ["Nested introduction"])

    def test_rejects_edges_to_unknown_nodes(self) -> None:
        spec = VisualSpec(
            schema_version="0.1",
            visual_type="process",
            title="Broken",
            description="Broken graph",
            confidence="medium",
            nodes=[VisualNode("known", "Known", "step", "Method", "Exact source")],
            edges=[VisualEdge("known", "missing")],
        )

        with self.assertRaises(VisualSpecError):
            validate_visual_spec(spec)


if __name__ == "__main__":
    unittest.main()
