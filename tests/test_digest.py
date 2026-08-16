from pathlib import Path
import unittest

from rpl.digest import build_digest
from rpl.parser import parse_arxiv_html
from rpl.render import knowledge_payload, render_markdown


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
        self.assertEqual(self.digest.problem.section, "Abstract")
        self.assertIn("role-aligned", self.digest.core_idea.text)

    def test_keeps_evidence_and_limitations_sourced(self) -> None:
        self.assertGreaterEqual(len(self.digest.evidence), 2)
        self.assertTrue(all(item.section for item in self.digest.evidence))
        self.assertGreaterEqual(len(self.digest.limitations), 2)
        self.assertTrue(any("synthetic" in item.text.lower() for item in self.digest.limitations))

    def test_renders_human_and_agent_outputs(self) -> None:
        markdown = render_markdown(self.paper, self.digest)
        payload = knowledge_payload(self.paper, self.digest)
        self.assertIn("## The core idea", markdown)
        self.assertIn("```mermaid", markdown)
        self.assertFalse(payload["provenance"]["generated_claims"])
        self.assertEqual(payload["schema_version"], "0.1")


if __name__ == "__main__":
    unittest.main()
