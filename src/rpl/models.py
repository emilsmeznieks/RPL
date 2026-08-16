from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Section:
    """A logical section extracted from a research paper."""

    title: str
    level: int
    paragraphs: list[str] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)

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


@dataclass(slots=True)
class Digest:
    """The small, useful layer RPL derives from a parsed paper."""

    problem: SourcedStatement | None
    core_idea: SourcedStatement | None
    evidence: list[SourcedStatement]
    limitations: list[SourcedStatement]
    takeaways: list[SourcedStatement]
    extraction_method: str = "deterministic-extractive-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

