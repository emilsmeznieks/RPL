import unittest

from rpl.source import SourceError, arxiv_id, normalize_arxiv_url


class SourceTests(unittest.TestCase):
    def test_normalizes_common_arxiv_inputs(self) -> None:
        expected = "https://arxiv.org/html/2607.17331v1"
        self.assertEqual(normalize_arxiv_url("2607.17331v1"), expected)
        self.assertEqual(normalize_arxiv_url("https://arxiv.org/abs/2607.17331v1"), expected)
        self.assertEqual(normalize_arxiv_url("https://arxiv.org/pdf/2607.17331v1"), expected)
        self.assertEqual(
            normalize_arxiv_url("https://export.arxiv.org/abs/2607.17331v1"),
            expected,
        )
        self.assertEqual(arxiv_id(expected), "2607.17331v1")

    def test_normalizes_legacy_arxiv_inputs(self) -> None:
        expected = "https://arxiv.org/html/hep-th/9901001v2"
        self.assertEqual(normalize_arxiv_url("hep-th/9901001v2"), expected)
        self.assertEqual(
            normalize_arxiv_url("https://arxiv.org/abs/hep-th/9901001v2"),
            expected,
        )
        self.assertEqual(
            arxiv_id("https://arxiv.org/pdf/math.GT/0309136"),
            "math.GT/0309136",
        )

    def test_rejects_non_arxiv_and_lookalike_urls(self) -> None:
        for value in (
            "https://example.com/abs/2607.17331v1",
            "https://arxiv.org.example.com/abs/2607.17331v1",
            "https://evil-arxiv.org/abs/2607.17331v1",
            "https://arxiv.org@evil.example/abs/2607.17331v1",
            "ftp://arxiv.org/abs/2607.17331v1",
        ):
            with self.subTest(value=value), self.assertRaises(SourceError):
                normalize_arxiv_url(value)

    def test_rejects_unknown_legacy_archive(self) -> None:
        with self.assertRaises(SourceError):
            normalize_arxiv_url("unknown/9901001")

    def test_rejects_values_without_an_identifier(self) -> None:
        with self.assertRaises(SourceError):
            normalize_arxiv_url("not-a-paper")


if __name__ == "__main__":
    unittest.main()
