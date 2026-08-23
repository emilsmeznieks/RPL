from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rpl.discovery import DiscoveryError
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
            "&quot;schema_version&quot;: &quot;0.9&quot;", self.analysis.html
        )
        self.assertEqual(self.analysis.output_quality.status, "ready")

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

    def test_remote_analysis_runs_related_paper_discovery(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        comparison = replace(
            self.analysis.comparison,
            status="no-match",
            discovery_method="test-discovery-v1",
        )
        with (
            patch(
                "rpl.service.read_source",
                return_value=(html, "https://arxiv.org/html/2607.17331v1"),
            ),
            patch(
                "rpl.service.discover_related_papers",
                return_value=comparison,
            ) as discover,
        ):
            analysis = analyze_source("2607.17331v1")

        discover.assert_called_once()
        self.assertEqual(analysis.comparison.status, "no-match")

    def test_remote_analysis_survives_discovery_failure(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        with (
            patch(
                "rpl.service.read_source",
                return_value=(html, "https://arxiv.org/html/2607.17331v1"),
            ),
            patch(
                "rpl.service.discover_related_papers",
                side_effect=DiscoveryError("offline"),
            ),
        ):
            analysis = analyze_source("2607.17331v1")

        self.assertEqual(analysis.comparison.status, "not-generated")
        self.assertEqual(
            analysis.comparison.discovery_method, "arxiv-api-unavailable-v1"
        )


if __name__ == "__main__":
    unittest.main()
