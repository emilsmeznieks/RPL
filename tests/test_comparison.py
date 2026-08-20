from dataclasses import replace
import unittest

from rpl.comparison import (
    ComparisonSpecError,
    empty_comparison_set,
    validate_comparison_set,
)
from rpl.models import (
    ComparisonDimension,
    ComparisonEvidence,
    ComparisonSet,
    ComparisonValue,
    Digest,
    Paper,
    RelatedPaper,
    RelationSignal,
    Section,
)
from rpl.render import knowledge_payload


class ComparisonModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.focal = Paper(
            paper_id="2607.17331v1",
            title="Agentic ERP",
            authors=["Researcher One"],
            published="2026-07-19",
            source_url="https://arxiv.org/html/2607.17331v1",
            abstract="A multi-agent architecture for enterprise resource planning.",
            sections=[Section(title="Architecture", level=2)],
        )
        self.related = RelatedPaper(
            paper_id="2606.10000v2",
            title="Auditable Enterprise Agents",
            authors=["Researcher Two"],
            published="2026-06-10",
            source_url="https://arxiv.org/html/2606.10000v2",
        )
        self.spec = ComparisonSet(
            schema_version="0.1",
            focal_paper_id=self.focal.paper_id,
            status="complete",
            related_papers=[self.related],
            relation_signals=[
                RelationSignal(
                    related_paper_id=self.related.paper_id,
                    kind="shared-method",
                    confidence="high",
                    evidence=[
                        ComparisonEvidence(
                            paper_id=self.focal.paper_id,
                            text="The system separates planning, execution, and validation agents.",
                            section="Architecture",
                            source_anchor="S3.p1",
                        ),
                        ComparisonEvidence(
                            paper_id=self.related.paper_id,
                            text="Independent agents plan, execute, and verify each workflow.",
                            section="Method",
                            source_anchor="S2.p4",
                        ),
                    ],
                )
            ],
            dimensions=[
                ComparisonDimension(
                    key="agent-structure",
                    label="Agent structure",
                    values=[
                        ComparisonValue(
                            paper_id=self.focal.paper_id,
                            text="Role-aligned agents operate across four architectural layers.",
                            section="Architecture",
                            source_anchor="S3.p2",
                        ),
                        ComparisonValue(
                            paper_id=self.related.paper_id,
                            text="Three independent agents handle each workflow.",
                            section="Method",
                            source_anchor="S2.p5",
                        ),
                    ],
                )
            ],
            discovery_method="arxiv-metadata-and-text-v1",
            generated_claims=False,
        )

    def test_empty_model_states_that_discovery_has_not_run(self) -> None:
        spec = empty_comparison_set(self.focal)

        validate_comparison_set(spec)
        self.assertEqual(spec.status, "not-generated")
        self.assertEqual(spec.discovery_method, "not-run")
        self.assertEqual(spec.related_papers, [])
        self.assertFalse(spec.generated_claims)

    def test_validates_and_serializes_a_sourced_comparison(self) -> None:
        validate_comparison_set(self.spec)

        payload = self.spec.to_dict()
        self.assertEqual(payload["schema_version"], "0.1")
        self.assertEqual(
            payload["relation_signals"][0]["evidence"][1]["source_anchor"],
            "S2.p4",
        )
        self.assertEqual(
            payload["dimensions"][0]["values"][0]["paper_id"],
            self.focal.paper_id,
        )

    def test_knowledge_payload_accepts_a_complete_comparison(self) -> None:
        digest = Digest(None, None, [], [], [])

        payload = knowledge_payload(self.focal, digest, self.spec)

        self.assertEqual(payload["schema_version"], "0.8")
        self.assertEqual(payload["comparison"]["status"], "complete")
        self.assertEqual(
            payload["comparison"]["related_papers"][0]["paper_id"],
            self.related.paper_id,
        )

    def test_knowledge_payload_rejects_a_different_focal_paper(self) -> None:
        digest = Digest(None, None, [], [], [])
        invalid = replace(self.spec, focal_paper_id="different-paper")

        with self.assertRaisesRegex(ValueError, "must match"):
            knowledge_payload(self.focal, digest, invalid)

    def test_partial_comparison_can_precede_dimension_extraction(self) -> None:
        partial = replace(self.spec, status="partial", dimensions=[])

        validate_comparison_set(partial)

    def test_rejects_a_relation_without_exact_evidence(self) -> None:
        invalid_signal = replace(self.spec.relation_signals[0], evidence=[])
        invalid = replace(self.spec, relation_signals=[invalid_signal])

        with self.assertRaisesRegex(ComparisonSpecError, "exact source evidence"):
            validate_comparison_set(invalid)

    def test_similarity_relation_requires_evidence_from_both_papers(self) -> None:
        focal_only = [self.spec.relation_signals[0].evidence[0]]
        invalid_signal = replace(
            self.spec.relation_signals[0], evidence=focal_only
        )
        invalid = replace(self.spec, relation_signals=[invalid_signal])

        with self.assertRaisesRegex(ComparisonSpecError, "both papers"):
            validate_comparison_set(invalid)

    def test_rejects_unknown_papers_in_comparison_dimensions(self) -> None:
        invalid_value = replace(
            self.spec.dimensions[0].values[1], paper_id="unknown-paper"
        )
        invalid_dimension = replace(
            self.spec.dimensions[0],
            values=[self.spec.dimensions[0].values[0], invalid_value],
        )
        invalid = replace(self.spec, dimensions=[invalid_dimension])

        with self.assertRaisesRegex(ComparisonSpecError, "focal paper"):
            validate_comparison_set(invalid)

    def test_rejects_duplicate_relation_kinds_for_the_same_pair(self) -> None:
        invalid = replace(
            self.spec,
            relation_signals=[
                self.spec.relation_signals[0],
                self.spec.relation_signals[0],
            ],
        )

        with self.assertRaisesRegex(ComparisonSpecError, "must be unique"):
            validate_comparison_set(invalid)


if __name__ == "__main__":
    unittest.main()
