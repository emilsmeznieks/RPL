from pathlib import Path
import unittest

from rpl.parser import PaperParseError, parse_arxiv_html


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paper = parse_arxiv_html(
            FIXTURE.read_text(encoding="utf-8"),
            "https://arxiv.org/html/2607.17331v1",
        )

    def test_reads_metadata_and_abstract(self) -> None:
        self.assertEqual(self.paper.paper_id, "2607.17331v1")
        self.assertEqual(len(self.paper.authors), 2)
        self.assertIn("Traditional enterprise software", self.paper.abstract)
        self.assertEqual(self.paper.keywords[0], "AI agents")

    def test_builds_sections_and_artifacts(self) -> None:
        self.assertEqual([section.title for section in self.paper.sections[:2]], ["Introduction", "Methodology"])
        methodology = self.paper.sections[1]
        self.assertEqual(methodology.level, 2)
        self.assertEqual(methodology.anchor, "S2")
        self.assertEqual(methodology.paragraph_anchors, ["S2.p1", "S2.p2"])
        self.assertIn("S = <S_inv, S_ord, S_fin>", methodology.equations)
        self.assertIn("guarded orchestration loop", methodology.figures[0])

    def test_rejects_empty_and_unrelated_html(self) -> None:
        for html in ("", "<html><body><h1>Not a paper</h1></body></html>"):
            with self.subTest(html=html), self.assertRaises(PaperParseError):
                parse_arxiv_html(html, "file:///tmp/input.html")

    def test_heading_inherits_its_enclosing_section_anchor(self) -> None:
        html = """
        <meta name="citation_title" content="Anchored paper">
        <div class="ltx_abstract"><p>A complete abstract for the anchored paper.</p></div>
        <section id="S1"><h2>Introduction</h2><p>A section paragraph.</p></section>
        """

        paper = parse_arxiv_html(html, "https://arxiv.org/html/2607.10000v1")

        self.assertEqual(paper.sections[0].anchor, "S1")
        self.assertEqual(paper.sections[0].paragraph_anchors, ["S1"])


if __name__ == "__main__":
    unittest.main()
