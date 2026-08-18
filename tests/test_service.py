import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rpl.service import analyze_source, safe_name, write_analysis


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class AnalysisServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = analyze_source(str(FIXTURE))

    def test_builds_all_outputs_from_one_analysis(self) -> None:
        self.assertEqual(self.analysis.paper.paper_id, "2607.17331v1")
        self.assertIn("## The core idea", self.analysis.markdown)
        self.assertTrue(self.analysis.html.startswith("<!doctype html>"))
        payload = json.loads(self.analysis.json)
        self.assertEqual(payload["comparison"]["status"], "not-generated")
        self.assertIn(
            "&quot;schema_version&quot;: &quot;0.6&quot;", self.analysis.html
        )

    def test_writes_selected_outputs_to_a_portable_paper_folder(self) -> None:
        with TemporaryDirectory() as directory:
            paths = write_analysis(
                self.analysis, directory, formats=("html", "json")
            )

            self.assertEqual([path.name for path in paths], ["paper.html", "paper.json"])
            self.assertTrue(all(path.is_absolute() for path in paths))
            self.assertTrue(all(path.parent.name == "2607.17331v1" for path in paths))
            self.assertFalse((paths[0].parent / "paper.md").exists())

    def test_rejects_unknown_output_formats(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unsupported output format"):
                write_analysis(self.analysis, directory, formats=("pdf",))

    def test_safe_name_handles_legacy_identifiers(self) -> None:
        self.assertEqual(safe_name("hep-th/9901001"), "hep-th-9901001")


if __name__ == "__main__":
    unittest.main()
