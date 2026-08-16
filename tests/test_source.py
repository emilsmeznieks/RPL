import unittest

from rpl.source import SourceError, arxiv_id, normalize_arxiv_url


class SourceTests(unittest.TestCase):
    def test_normalizes_common_arxiv_inputs(self) -> None:
        expected = "https://arxiv.org/html/2607.17331v1"
        self.assertEqual(normalize_arxiv_url("2607.17331v1"), expected)
        self.assertEqual(normalize_arxiv_url("https://arxiv.org/abs/2607.17331v1"), expected)
        self.assertEqual(normalize_arxiv_url("https://arxiv.org/pdf/2607.17331v1"), expected)
        self.assertEqual(arxiv_id(expected), "2607.17331v1")

    def test_rejects_values_without_an_identifier(self) -> None:
        with self.assertRaises(SourceError):
            normalize_arxiv_url("not-a-paper")


if __name__ == "__main__":
    unittest.main()
