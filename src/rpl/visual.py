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
ENCODER_DECODER_ARCHITECTURE_SIGNALS = (
    "encoder-decoder structure",
    "encoder maps an input sequence",
    "decoder then generates an output sequence",
)
ENCODER_STACK_SIGNALS = (
    "encoder is composed of a stack",
    "multi-head self-attention",
    "feed-forward network",
)
DECODER_STACK_SIGNALS = (
    "decoder is also composed of a stack",
    "attention over the output of the encoder",
    "prevent positions from attending to subsequent positions",
)
ENCODER_DECODER_ATTENTION_SIGNALS = (
    'in "encoder-decoder attention" layers',
    "queries come from the previous decoder layer",
    "memory keys and values come from the output of the encoder",
)


class VisualSpecError(ValueError):
    """Raised when a visual specification is internally inconsistent."""


def validate_visual_spec(spec: VisualSpec) -> None:
    """Fail fast if a renderer could not safely interpret the graph."""

    if spec.schema_version != "0.2":
        raise VisualSpecError(f"Unsupported visual schema: {spec.schema_version}")
    if spec.visual_type not in {
        "encoder-decoder",
        "process",
        "layered-architecture",
        "paper-outline",
    }:
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
                schema_version="0.2",
                visual_type="layered-architecture",
                title="System architecture",
                description="Architecture layers named in the paper.",
                confidence="medium",
                nodes=nodes,
                edges=edges,
            )
    return None


def _matching_paragraph(
    paper: Paper, signals: tuple[str, ...]
) -> tuple[Section, str, str | None] | None:
    for section in paper.sections:
        for index, paragraph in enumerate(section.paragraphs):
            lowered = paragraph.lower()
            if all(signal in lowered for signal in signals):
                anchor = (
                    section.paragraph_anchors[index]
                    if index < len(section.paragraph_anchors)
                    else section.anchor
                )
                return section, paragraph, anchor
    return None


def _encoder_decoder_spec(paper: Paper) -> VisualSpec | None:
    architecture = _matching_paragraph(paper, ENCODER_DECODER_ARCHITECTURE_SIGNALS)
    encoder = _matching_paragraph(paper, ENCODER_STACK_SIGNALS)
    decoder = _matching_paragraph(paper, DECODER_STACK_SIGNALS)
    cross_attention = _matching_paragraph(paper, ENCODER_DECODER_ATTENTION_SIGNALS)
    if not architecture or not encoder or not decoder or not cross_attention:
        return None

    architecture_section, architecture_text, architecture_anchor = architecture
    encoder_section, encoder_text, encoder_anchor = encoder
    decoder_section, decoder_text, decoder_anchor = decoder
    cross_section, cross_text, cross_anchor = cross_attention
    nodes = [
        VisualNode(
            "input",
            "Input sequence",
            "input",
            architecture_section.title,
            architecture_text,
            architecture_anchor,
            group="encoder",
        ),
        VisualNode(
            "encoder-attention",
            "Multi-head self-attention",
            "layer",
            encoder_section.title,
            encoder_text,
            encoder_anchor,
            group="encoder",
            detail="First sub-layer",
        ),
        VisualNode(
            "encoder-feed-forward",
            "Feed-forward network",
            "layer",
            encoder_section.title,
            encoder_text,
            encoder_anchor,
            group="encoder",
            detail="Second sub-layer",
        ),
        VisualNode(
            "previous-output",
            "Previous outputs",
            "input",
            architecture_section.title,
            architecture_text,
            architecture_anchor,
            group="decoder",
        ),
        VisualNode(
            "decoder-attention",
            "Masked self-attention",
            "layer",
            decoder_section.title,
            decoder_text,
            decoder_anchor,
            group="decoder",
            detail="Masks later positions",
        ),
        VisualNode(
            "cross-attention",
            "Encoder–decoder attention",
            "layer",
            cross_section.title,
            cross_text,
            cross_anchor,
            group="decoder",
            detail="Uses encoder output",
        ),
        VisualNode(
            "decoder-feed-forward",
            "Feed-forward network",
            "layer",
            decoder_section.title,
            decoder_text,
            decoder_anchor,
            group="decoder",
            detail="Feed-forward sub-layer",
        ),
        VisualNode(
            "output",
            "Output sequence",
            "output",
            architecture_section.title,
            architecture_text,
            architecture_anchor,
            group="decoder",
        ),
    ]
    edges = [
        VisualEdge("input", "encoder-attention"),
        VisualEdge("encoder-attention", "encoder-feed-forward"),
        VisualEdge("encoder-feed-forward", "cross-attention", "keys + values"),
        VisualEdge("previous-output", "decoder-attention"),
        VisualEdge("decoder-attention", "cross-attention", "queries"),
        VisualEdge("cross-attention", "decoder-feed-forward"),
        VisualEdge("decoder-feed-forward", "output"),
    ]
    return VisualSpec(
        schema_version="0.2",
        visual_type="encoder-decoder",
        title="Encoder–decoder architecture",
        description="The sourced information flow through the paper's model.",
        confidence="high",
        nodes=nodes,
        edges=edges,
    )


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
                    schema_version="0.2",
                    visual_type="process",
                    title="How the proposed system works",
                    description="Steps named in the paper.",
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
        schema_version="0.2",
        visual_type="paper-outline",
        title="Paper structure",
        description="Main sections in reading order.",
        confidence="low",
        nodes=nodes,
        edges=edges,
    )


def build_visual_spec(paper: Paper) -> VisualSpec:
    """Extract a conservative visual graph without generating new claims."""

    spec = (
        _encoder_decoder_spec(paper)
        or _architecture_spec(paper)
        or _process_spec(paper)
        or _outline_spec(paper)
    )
    validate_visual_spec(spec)
    return spec
