from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from rpl.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class CliTests(unittest.TestCase):
    def test_learn_writes_markdown_and_json(self) -> None:
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            result = main(["learn", str(FIXTURE), "--output", directory])
            destination = Path(directory) / "2607.17331v1"
            self.assertEqual(result, 0)
            self.assertTrue((destination / "paper.md").is_file())
            payload = json.loads((destination / "paper.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["paper"]["paper_id"], "2607.17331v1")


if __name__ == "__main__":
    unittest.main()

