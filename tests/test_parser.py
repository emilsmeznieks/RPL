from pathlib import Path
import unittest

from rpl.parser import parse_arxiv_html


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
        self.assertIn("S = <S_inv, S_ord, S_fin>", methodology.equations)
        self.assertIn("guarded orchestration loop", methodology.figures[0])


if __name__ == "__main__":
    unittest.main()

