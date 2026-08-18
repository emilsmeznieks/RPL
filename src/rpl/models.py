from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Section:
    """A logical section extracted from a research paper."""

    title: str
    level: int
    anchor: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    paragraph_anchors: list[str | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Paper:
    """Provider-neutral paper representation used by every RPL output."""

    paper_id: str
    title: str
    authors: list[str]
    published: str | None
    source_url: str
    abstract: str
    keywords: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourcedStatement:
    """An extractive statement and the section that supports it."""

    text: str
    section: str
    section_anchor: str | None = None
    source_anchor: str | None = None


@dataclass(slots=True)
class Digest:
    """The small, useful layer RPL derives from a parsed paper."""

    problem: SourcedStatement | None
    core_idea: SourcedStatement | None
    evidence: list[SourcedStatement]
    limitations: list[SourcedStatement]
    takeaways: list[SourcedStatement]
    extraction_method: str = "deterministic-extractive-v1"
    paper_type: str = "unknown"
    paper_type_confidence: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VisualNode:
    """A sourced concept that can be rendered by any visual frontend."""

    id: str
    label: str
    kind: str
    source_section: str
    source_text: str
    source_anchor: str | None = None


@dataclass(slots=True)
class VisualEdge:
    """A directed relationship between two visual nodes."""

    source: str
    target: str
    label: str = "next"


@dataclass(slots=True)
class VisualSpec:
    """Provider-neutral instructions for a paper-specific visual explanation."""

    schema_version: str
    visual_type: str
    title: str
    description: str
    confidence: str
    nodes: list[VisualNode]
    edges: list[VisualEdge]
    extraction_method: str = "deterministic-visual-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GlossaryTerm:
    """A short form and its meaning as defined by the paper."""

    short_form: str
    term: str
    source_section: str
    source_text: str
    source_anchor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RelatedPaper:
    """Metadata for a paper compared with the focal paper."""

    paper_id: str
    title: str
    authors: list[str]
    published: str | None
    source_url: str


@dataclass(slots=True)
class ComparisonEvidence:
    """Exact paper text supporting a relationship between two papers."""

    paper_id: str
    text: str
    section: str
    source_anchor: str | None = None


@dataclass(slots=True)
class RelationSignal:
    """A sourced reason that a candidate paper is related to the focal paper."""

    related_paper_id: str
    kind: str
    confidence: str
    evidence: list[ComparisonEvidence]


@dataclass(slots=True)
class ComparisonValue:
    """One paper's sourced value for a comparison dimension."""

    paper_id: str
    text: str
    section: str
    source_anchor: str | None = None


@dataclass(slots=True)
class ComparisonDimension:
    """A named question answered side by side for two or more papers."""

    key: str
    label: str
    values: list[ComparisonValue]


@dataclass(slots=True)
class ComparisonSet:
    """Provider-neutral, evidence-backed related-paper comparison data."""

    schema_version: str
    focal_paper_id: str
    status: str
    related_papers: list[RelatedPaper]
    relation_signals: list[RelationSignal]
    dimensions: list[ComparisonDimension]
    discovery_method: str
    generated_claims: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
