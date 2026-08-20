import unittest

from rpl.models import Digest, Paper, Section, VisualEdge, VisualNode, VisualSpec
from rpl.parser import parse_arxiv_html
from rpl.render import render_html
from rpl.visual import VisualSpecError, build_visual_spec, validate_visual_spec


class VisualSpecTests(unittest.TestCase):
    def test_extracts_a_sourced_encoder_decoder_architecture(self) -> None:
        architecture = (
            "The model has an encoder-decoder structure. The encoder maps an input "
            "sequence to continuous representations. The decoder then generates an "
            "output sequence one element at a time."
        )
        encoder = (
            "The encoder is composed of a stack of N=6 identical layers. The first "
            "sub-layer is multi-head self-attention and the second is a feed-forward network."
        )
        decoder = (
            "The decoder is also composed of a stack of N=6 identical layers. It performs "
            "attention over the output of the encoder and uses masking to prevent positions "
            "from attending to subsequent positions."
        )
        cross_attention = (
            'In "encoder-decoder attention" layers, the queries come from the previous '
            "decoder layer, and the memory keys and values come from the output of the encoder."
        )
        paper = Paper(
            paper_id="paper",
            title="Encoder-decoder model",
            authors=[],
            published=None,
            source_url="https://arxiv.org/html/1706.03762",
            abstract="We propose an attention model for sequence transduction.",
            sections=[
                Section(
                    "Model Architecture",
                    2,
                    anchor="S3",
                    paragraphs=[architecture],
                    paragraph_anchors=["S3.p1"],
                ),
                Section(
                    "Encoder and Decoder Stacks",
                    3,
                    anchor="S3.SS1",
                    paragraphs=[encoder, decoder],
                    paragraph_anchors=["S3.SS1.p1", "S3.SS1.p2"],
                ),
                Section(
                    "Applications of Attention",
                    3,
                    anchor="S3.SS2",
                    paragraphs=[cross_attention],
                    paragraph_anchors=["S3.SS2.p1"],
                ),
            ],
        )

        visual = build_visual_spec(paper)

        self.assertEqual(visual.schema_version, "0.2")
        self.assertEqual(visual.visual_type, "encoder-decoder")
        self.assertEqual(visual.confidence, "high")
        self.assertEqual(len(visual.nodes), 8)
        self.assertEqual(
            [node.group for node in visual.nodes],
            ["encoder", "encoder", "encoder", "decoder", "decoder", "decoder", "decoder", "decoder"],
        )
        self.assertIn(
            ("encoder-feed-forward", "cross-attention", "keys + values"),
            [(edge.source, edge.target, edge.label) for edge in visual.edges],
        )
        self.assertEqual(visual.nodes[1].source_anchor, "S3.SS1.p1")
        self.assertEqual(visual.nodes[5].source_anchor, "S3.SS2.p1")

        html = render_html(
            paper,
            Digest(None, None, [], [], []),
        )
        self.assertIn("Encoder–decoder architecture", html)
        self.assertIn("Repeated layer stack", html)
        self.assertIn("Keys + values", html)
        self.assertIn("Encoder stack</a>", html)
        self.assertIn("Decoder stack</a>", html)
        self.assertIn("Encoder–decoder attention</a>", html)
        self.assertIn("#S3.SS1.p1", html)
        self.assertIn("#S3.SS1.p2", html)
        self.assertIn("#S3.SS2.p1", html)
        self.assertNotIn("Paper structure", html)

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
        <p id="S2.p1">Requests pass through plan, execute, reflect, and respond stages.</p>
        """
        paper = parse_arxiv_html(html, "https://arxiv.org/html/2607.10000v1")

        visual = build_visual_spec(paper)

        self.assertEqual(visual.visual_type, "process")
        self.assertEqual([node.label for node in visual.nodes], ["Plan", "Execute", "Reflect", "Respond"])
        self.assertTrue(all(node.source_section == "Method" for node in visual.nodes))
        self.assertTrue(all(node.source_anchor == "S2.p1" for node in visual.nodes))
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
            schema_version="0.2",
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
