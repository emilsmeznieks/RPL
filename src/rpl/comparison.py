from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import ComparisonSet, Paper


COMPARISON_SCHEMA_VERSION = "0.1"
COMPARISON_STATUSES = {"not-generated", "partial", "complete"}
RELATION_KINDS = {
    "same-topic",
    "shared-task",
    "shared-method",
    "shared-equation",
    "shared-dataset",
    "cites",
    "cited-by",
}
CONFIDENCE_LEVELS = {"low", "moderate", "high"}
DIMENSION_KEY = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class ComparisonSpecError(ValueError):
    """Raised when related-paper comparison data is internally inconsistent."""


def empty_comparison_set(paper: Paper) -> ComparisonSet:
    """Represent that comparison discovery has not run without implying a result."""

    return ComparisonSet(
        schema_version=COMPARISON_SCHEMA_VERSION,
        focal_paper_id=paper.paper_id,
        status="not-generated",
        related_papers=[],
        relation_signals=[],
        dimensions=[],
        discovery_method="not-run",
        generated_claims=False,
    )


def validate_comparison_set(spec: ComparisonSet) -> None:
    """Fail fast when agents or renderers could misread comparison data."""

    if spec.schema_version != COMPARISON_SCHEMA_VERSION:
        raise ComparisonSpecError(
            f"Unsupported comparison schema: {spec.schema_version}"
        )
    if not spec.focal_paper_id.strip():
        raise ComparisonSpecError("A comparison needs a focal paper identifier.")
    if spec.status not in COMPARISON_STATUSES:
        raise ComparisonSpecError(f"Unsupported comparison status: {spec.status}")
    if not spec.discovery_method.strip():
        raise ComparisonSpecError("A comparison needs a discovery method.")
    if not isinstance(spec.generated_claims, bool):
        raise ComparisonSpecError("generated_claims must be true or false.")

    if spec.status == "not-generated":
        if spec.generated_claims:
            raise ComparisonSpecError(
                "A comparison that was not generated cannot contain generated claims."
            )
        if spec.related_papers or spec.relation_signals or spec.dimensions:
            raise ComparisonSpecError(
                "A comparison that was not generated cannot contain results."
            )
        return

    if not spec.related_papers:
        raise ComparisonSpecError("A generated comparison needs a related paper.")

    related_ids = [paper.paper_id for paper in spec.related_papers]
    if len(related_ids) != len(set(related_ids)):
        raise ComparisonSpecError("Related paper identifiers must be unique.")
    if spec.focal_paper_id in related_ids:
        raise ComparisonSpecError("The focal paper cannot also be a related paper.")
    if any(
        not paper.paper_id.strip()
        or not paper.title.strip()
        or urlparse(paper.source_url).scheme not in {"http", "https"}
        or not urlparse(paper.source_url).netloc
        for paper in spec.related_papers
    ):
        raise ComparisonSpecError(
            "Every related paper needs an identifier, title, and HTTP source URL."
        )

    known_ids = {spec.focal_paper_id, *related_ids}
    signal_keys: list[tuple[str, str]] = []
    signaled_ids: set[str] = set()
    for signal in spec.relation_signals:
        if signal.related_paper_id not in related_ids:
            raise ComparisonSpecError("Every relation must reference a related paper.")
        if signal.kind not in RELATION_KINDS:
            raise ComparisonSpecError(f"Unsupported relation kind: {signal.kind}")
        if signal.confidence not in CONFIDENCE_LEVELS:
            raise ComparisonSpecError(
                f"Unsupported relation confidence: {signal.confidence}"
            )
        if not signal.evidence:
            raise ComparisonSpecError("Every relation needs exact source evidence.")
        if any(
            evidence.paper_id
            not in {spec.focal_paper_id, signal.related_paper_id}
            or not evidence.text.strip()
            or not evidence.section.strip()
            for evidence in signal.evidence
        ):
            raise ComparisonSpecError(
                "Relation evidence must come from one of the related paper pair."
            )
        evidence_ids = {evidence.paper_id for evidence in signal.evidence}
        if signal.kind not in {"cites", "cited-by"} and evidence_ids != {
            spec.focal_paper_id,
            signal.related_paper_id,
        }:
            raise ComparisonSpecError(
                "A similarity relation needs evidence from both papers."
            )
        signal_keys.append((signal.related_paper_id, signal.kind))
        signaled_ids.add(signal.related_paper_id)

    if len(signal_keys) != len(set(signal_keys)):
        raise ComparisonSpecError("Relation kinds must be unique for each paper pair.")
    if signaled_ids != set(related_ids):
        raise ComparisonSpecError("Every related paper needs a sourced relation signal.")

    dimension_keys = [dimension.key for dimension in spec.dimensions]
    if len(dimension_keys) != len(set(dimension_keys)):
        raise ComparisonSpecError("Comparison dimension keys must be unique.")
    for dimension in spec.dimensions:
        if not DIMENSION_KEY.fullmatch(dimension.key) or not dimension.label.strip():
            raise ComparisonSpecError(
                "Every comparison dimension needs a stable key and readable label."
            )
        value_ids = [value.paper_id for value in dimension.values]
        if len(value_ids) != len(set(value_ids)):
            raise ComparisonSpecError(
                "A dimension can contain only one value for each paper."
            )
        if (
            len(value_ids) < 2
            or spec.focal_paper_id not in value_ids
            or any(paper_id not in known_ids for paper_id in value_ids)
        ):
            raise ComparisonSpecError(
                "Each dimension must compare the focal paper with a related paper."
            )
        if any(
            not value.text.strip() or not value.section.strip()
            for value in dimension.values
        ):
            raise ComparisonSpecError(
                "Every comparison value needs exact text and a source section."
            )

    if spec.status == "complete" and not spec.dimensions:
        raise ComparisonSpecError("A complete comparison needs comparison dimensions.")
