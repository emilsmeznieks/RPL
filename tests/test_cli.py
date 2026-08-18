from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from rpl.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class CliTests(unittest.TestCase):
    def test_learn_writes_all_formats(self) -> None:
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            result = main(["learn", str(FIXTURE), "--output", directory])
            destination = Path(directory) / "2607.17331v1"
            self.assertEqual(result, 0)
            self.assertTrue((destination / "paper.md").is_file())
            self.assertTrue((destination / "paper.html").is_file())
            payload = json.loads((destination / "paper.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["paper"]["paper_id"], "2607.17331v1")

    def test_html_format_writes_only_html(self) -> None:
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            result = main(["learn", str(FIXTURE), "--output", directory, "--format", "html"])
            destination = Path(directory) / "2607.17331v1"
            self.assertEqual(result, 0)
            self.assertTrue((destination / "paper.html").is_file())
            self.assertFalse((destination / "paper.md").exists())
            self.assertFalse((destination / "paper.json").exists())

    def test_invalid_html_returns_readable_error(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.html"
            source.write_text("<html><h1>Not an arXiv paper</h1></html>", encoding="utf-8")
            errors = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(errors):
                result = main(["learn", str(source)])
            self.assertEqual(result, 1)
            self.assertIn("does not look like a supported arXiv HTML paper", errors.getvalue())

    def test_rejects_non_positive_timeout(self) -> None:
        for value in ("-1", "0", "nan", "inf"):
            with self.subTest(value=value):
                errors = StringIO()
                with redirect_stderr(errors), self.assertRaises(SystemExit) as context:
                    main(["learn", str(FIXTURE), "--timeout", value])
                self.assertEqual(context.exception.code, 2)
                self.assertIn("must be a finite number greater than zero", errors.getvalue())

    def test_output_write_failure_returns_readable_error(self) -> None:
        with TemporaryDirectory() as directory:
            output_file = Path(directory) / "already-a-file"
            output_file.write_text("occupied", encoding="utf-8")
            errors = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(errors):
                result = main(["learn", str(FIXTURE), "--output", str(output_file)])
            self.assertEqual(result, 1)
            self.assertIn("Could not write output", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
