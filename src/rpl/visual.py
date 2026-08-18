from __future__ import annotations

import re

from .models import Paper, Section, VisualEdge, VisualNode, VisualSpec


METHOD_SECTION_SIGNALS = (
    "method",
    "approach",
    "architecture",
    "framework",
    "system",
    "model",
    "implementation",
)
SEQUENCE_PATTERN = re.compile(
    r"\b(?:through|across|via)\s+([^.;:]{8,180})(?=[.;:]|$)", re.I
)
TRAILING_STAGE = re.compile(r"\s+(?:stages?|steps?|phases?)\s*$", re.I)
SEQUENCE_SEPARATOR = re.compile(r"\s*,\s*|\s+(?:and|then)\s+", re.I)
SAFE_LABEL = re.compile(r"^[\w][\w /+&-]*$", re.UNICODE)
ARCHITECTURE_VERBS = re.compile(
    r"^(.{2,60}?)\s+(?:handles?|manages?|provides?|ensures?|coordinates?|contains?|supports?)\b",
    re.I,
)


class VisualSpecError(ValueError):
    """Raised when a visual specification is internally inconsistent."""


def validate_visual_spec(spec: VisualSpec) -> None:
    """Fail fast if a renderer could not safely interpret the graph."""

    if spec.schema_version != "0.1":
        raise VisualSpecError(f"Unsupported visual schema: {spec.schema_version}")
    if spec.visual_type not in {"process", "layered-architecture", "paper-outline"}:
        raise VisualSpecError(f"Unsupported visual type: {spec.visual_type}")
    if spec.confidence not in {"low", "medium", "high"}:
        raise VisualSpecError(f"Unsupported confidence: {spec.confidence}")
    if not 1 <= len(spec.nodes) <= 8:
        raise VisualSpecError("A visual must contain between 1 and 8 nodes.")

    node_ids = [node.id for node in spec.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise VisualSpecError("Visual node identifiers must be unique.")
    if any(
        not node.label.strip()
        or not node.source_section.strip()
        or not node.source_text.strip()
        for node in spec.nodes
    ):
        raise VisualSpecError("Every visual node needs a label and exact source text.")
    known = set(node_ids)
    if any(edge.source not in known or edge.target not in known for edge in spec.edges):
        raise VisualSpecError("Every visual edge must connect known nodes.")


def _method_sections(paper: Paper) -> list[Section]:
    matching = [
        section
        for section in paper.sections
        if any(signal in section.title.lower() for signal in METHOD_SECTION_SIGNALS)
    ]
    return matching or paper.sections


def _sequence_items(fragment: str) -> list[str]:
    fragment = TRAILING_STAGE.sub("", fragment).strip()
    items = [item.strip(" -–—()") for item in SEQUENCE_SEPARATOR.split(fragment)]
    items = [re.sub(r"^(?:and|then)\s+", "", item, flags=re.I) for item in items]
    items = [item for item in items if item]
    if not 3 <= len(items) <= 7:
        return []
    if any(len(item.split()) > 4 or not SAFE_LABEL.fullmatch(item) for item in items):
        return []
    return items


def _architecture_items(caption: str) -> list[str]:
    if ":" not in caption or "architect" not in caption.lower() or "layer" not in caption.lower():
        return []
    clauses = re.split(r"\s*,\s*", caption.rsplit(":", 1)[1])
    items: list[str] = []
    for clause in clauses:
        clause = re.sub(r"^(?:and\s+)?(?:the\s+)?", "", clause.strip(), flags=re.I)
        match = ARCHITECTURE_VERBS.match(clause)
        if not match:
            return []
        label = match.group(1).strip()
        if len(label.split()) > 5 or not SAFE_LABEL.fullmatch(label):
            return []
        items.append(label)
    return items if 3 <= len(items) <= 6 else []


def _architecture_spec(paper: Paper) -> VisualSpec | None:
    for section in _method_sections(paper):
        for caption in section.figures:
            items = _architecture_items(caption)
            if not items:
                continue
            nodes = [
                VisualNode(
                    id=f"layer-{index}",
                    label=item,
                    kind="layer",
                    source_section=section.title,
                    source_text=caption,
                    source_anchor=section.anchor,
                )
                for index, item in enumerate(items, start=1)
            ]
            edges = [
                VisualEdge(
                    source=nodes[index].id,
                    target=nodes[index + 1].id,
                    label="next layer",
                )
                for index in range(len(nodes) - 1)
            ]
            return VisualSpec(
                schema_version="0.1",
                visual_type="layered-architecture",
                title="System architecture",
                description=f"Architectural layers extracted from a figure in {section.title}.",
                confidence="medium",
                nodes=nodes,
                edges=edges,
            )
    return None


def _process_spec(paper: Paper) -> VisualSpec | None:
    for section in _method_sections(paper):
        for paragraph_index, paragraph in enumerate(section.paragraphs):
            source_anchor = (
                section.paragraph_anchors[paragraph_index]
                if paragraph_index < len(section.paragraph_anchors)
                else section.anchor
            )
            for match in SEQUENCE_PATTERN.finditer(paragraph):
                items = _sequence_items(match.group(1))
                if not items:
                    continue
                nodes = [
                    VisualNode(
                        id=f"step-{index}",
                        label=item[0].upper() + item[1:] if item else item,
                        kind="step",
                        source_section=section.title,
                        source_text=paragraph,
                        source_anchor=source_anchor,
                    )
                    for index, item in enumerate(items, start=1)
                ]
                edges = [
                    VisualEdge(source=nodes[index].id, target=nodes[index + 1].id)
                    for index in range(len(nodes) - 1)
                ]
                return VisualSpec(
                    schema_version="0.1",
                    visual_type="process",
                    title="How the proposed system works",
                    description=f"A process sequence extracted from {section.title}.",
                    confidence="medium",
                    nodes=nodes,
                    edges=edges,
                )
    return None


def _outline_spec(paper: Paper) -> VisualSpec:
    major = [section for section in paper.sections if section.level == 2][:6]
    if not major:
        major = paper.sections[:6]
    nodes = [
        VisualNode(
            id=f"section-{index}",
            label=section.title,
            kind="section",
            source_section=section.title,
            source_text=section.title,
            source_anchor=section.anchor,
        )
        for index, section in enumerate(major, start=1)
    ]
    edges = [
        VisualEdge(source=nodes[index].id, target=nodes[index + 1].id)
        for index in range(len(nodes) - 1)
    ]
    return VisualSpec(
        schema_version="0.1",
        visual_type="paper-outline",
        title="Paper structure",
        description="A section-by-section view used because no explicit process was identified.",
        confidence="low",
        nodes=nodes,
        edges=edges,
    )


def build_visual_spec(paper: Paper) -> VisualSpec:
    """Extract a conservative visual graph without generating new claims."""

    spec = _architecture_spec(paper) or _process_spec(paper) or _outline_spec(paper)
    validate_visual_spec(spec)
    return spec
