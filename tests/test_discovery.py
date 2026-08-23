import unittest

from rpl.discovery import (
    ArxivCandidate,
    DiscoveryError,
    build_discovery_url,
    discover_related_papers,
    parse_arxiv_feed,
    search_terms,
)
from rpl.models import Digest, Paper, SourcedStatement


FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>The Transformer uses attention for sequence transduction.</summary>
    <author><name>A. Researcher</name></author>
    <category term="cs.CL"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1801.00001v2</id>
    <published>2018-01-01T12:00:00Z</published>
    <title>Efficient Attention for Sequence Translation</title>
    <summary>We present an efficient attention architecture for sequence translation. The method improves parallel training.</summary>
    <author><name>B. Researcher</name></author>
    <category term="cs.CL"/>
  </entry>
</feed>
"""


class RelatedPaperDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paper = Paper(
            paper_id="1706.03762v1",
            title="Attention Is All You Need",
            authors=["A. Researcher"],
            published="2017-06-12",
            source_url="https://arxiv.org/html/1706.03762v1",
            abstract=(
                "We propose the Transformer, an attention architecture for sequence "
                "transduction. It improves parallel training for translation tasks."
            ),
        )
        self.digest = Digest(
            problem=None,
            core_idea=SourcedStatement(
                "We propose the Transformer, an attention architecture for sequence transduction.",
                "Abstract",
            ),
            evidence=[],
            limitations=[],
            takeaways=[],
        )

    def test_builds_a_small_query_from_paper_words(self) -> None:
        terms = search_terms(self.paper)
        url = build_discovery_url(self.paper)

        self.assertIn("attention", terms)
        self.assertIn("transformer", terms)
        self.assertIn("search_query=", url)
        self.assertIn("max_results=20", url)
        self.assertIn("sortBy=relevance", url)

    def test_parses_documented_atom_metadata(self) -> None:
        candidates = parse_arxiv_feed(FEED)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[1].paper_id, "1801.00001v2")
        self.assertEqual(candidates[1].authors, ["B. Researcher"])
        self.assertEqual(candidates[1].published, "2018-01-01")
        self.assertEqual(candidates[1].categories, ["cs.CL"])

    def test_populates_an_evidence_backed_comparison(self) -> None:
        comparison = discover_related_papers(
            self.paper,
            self.digest,
            candidates=parse_arxiv_feed(FEED),
        )

        self.assertEqual(comparison.schema_version, "0.2")
        self.assertEqual(comparison.status, "complete")
        self.assertEqual(
            [paper.paper_id for paper in comparison.related_papers],
            ["1801.00001v2"],
        )
        signal = comparison.relation_signals[0]
        self.assertEqual(signal.kind, "same-topic")
        self.assertEqual(
            {evidence.paper_id for evidence in signal.evidence},
            {"1706.03762v1", "1801.00001v2"},
        )
        self.assertTrue(all(item.section == "Abstract" for item in signal.evidence))
        self.assertEqual(comparison.dimensions[0].key, "abstract-focus")
        self.assertFalse(comparison.generated_claims)

    def test_records_a_completed_search_with_no_safe_match(self) -> None:
        unrelated = ArxivCandidate(
            paper_id="2201.10000v1",
            title="Marine Sediment Measurements",
            authors=["C. Researcher"],
            published="2022-01-20",
            abstract="We measure coastal sediment movement during winter storms.",
            categories=["physics.geo-ph"],
        )

        comparison = discover_related_papers(
            self.paper, self.digest, candidates=[unrelated]
        )

        self.assertEqual(comparison.status, "no-match")
        self.assertEqual(comparison.related_papers, [])
        self.assertNotEqual(comparison.discovery_method, "not-run")

    def test_uses_an_exact_title_when_it_is_the_strongest_relation_evidence(self) -> None:
        candidate = ArxivCandidate(
            paper_id="2501.10000v1",
            title="Transformer Attention Architecture Analysis",
            authors=["D. Researcher"],
            published="2025-01-20",
            abstract="We evaluate accuracy across several benchmark collections.",
            categories=["cs.LG"],
        )

        comparison = discover_related_papers(
            self.paper, self.digest, candidates=[candidate]
        )

        related_evidence = comparison.relation_signals[0].evidence[1]
        self.assertEqual(related_evidence.section, "Title")
        self.assertEqual(related_evidence.text, candidate.title)

    def test_rejects_invalid_atom_xml(self) -> None:
        with self.assertRaises(DiscoveryError):
            parse_arxiv_feed("<feed>")


if __name__ == "__main__":
    unittest.main()
