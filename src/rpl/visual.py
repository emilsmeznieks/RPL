from __future__ import annotations

import re

from .models import (
    Paper,
    ScoringLevel,
    ScoringSpec,
    Section,
    VisualEdge,
    VisualNode,
    VisualSpec,
)


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

    if spec.schema_version != "0.3":
        raise VisualSpecError(f"Unsupported visual schema: {spec.schema_version}")
    if spec.visual_type not in {
        "benchmark-process",
        "change-layers",
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


def _figure_captions(section: Section) -> list[tuple[str, str | None]]:
    if section.figure_records:
        return [(record.caption, record.anchor or section.anchor) for record in section.figure_records]
    return [(caption, section.anchor) for caption in section.figures]


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
        for caption, caption_anchor in _figure_captions(section):
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
                    source_anchor=caption_anchor,
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
                schema_version="0.3",
                visual_type="layered-architecture",
                title="System architecture",
                description="Architecture layers named in the paper.",
                confidence="medium",
                nodes=nodes,
                edges=edges,
            )
    return None


def _paragraph_with_signals(
    paper: Paper, signals: tuple[str, ...], *, title_signal: str | None = None
) -> tuple[Section, str, str | None] | None:
    for section in paper.sections:
        if title_signal and title_signal not in section.title.lower():
            continue
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


def _benchmark_process_spec(paper: Paper) -> VisualSpec | None:
    caption_match: tuple[Section, str, str | None] | None = None
    for section in paper.sections:
        for caption, anchor in _figure_captions(section):
            lowered = caption.lower()
            required = (
                "lifecycle",
                "repository",
                "four hours",
                "source-code patch",
                "fresh container",
                "twelve hours",
                "evaluator",
            )
            if all(signal in lowered for signal in required):
                caption_match = (section, caption, anchor)
                break
        if caption_match:
            break
    if not caption_match:
        return None

    exploration = _paragraph_with_signals(
        paper, ("four hours", "one b300", "only the source"), title_signal="protocol"
    )
    verification = _paragraph_with_signals(
        paper, ("initialization", "twelve hours", "scored"), title_signal="protocol"
    )
    evaluator = _paragraph_with_signals(
        paper, ("final metric", "evaluator frozen", "agent"), title_signal="protocol"
    )
    scoring = _paragraph_with_signals(
        paper, ("two branches", "0.1", "optimum"), title_signal="scor"
    )
    if not exploration or not verification or not evaluator or not scoring:
        return None

    caption_section, caption, caption_anchor = caption_match
    exploration_section, exploration_text, exploration_anchor = exploration
    verification_section, verification_text, verification_anchor = verification
    evaluator_section, evaluator_text, evaluator_anchor = evaluator
    scoring_section, scoring_text, scoring_anchor = scoring
    nodes = [
        VisualNode(
            "frozen-inputs",
            "Frozen repository, starting model, and proxy metric",
            "input",
            caption_section.title,
            caption,
            caption_anchor,
        ),
        VisualNode(
            "exploration",
            "Four-hour agent exploration on one B300",
            "step",
            exploration_section.title,
            exploration_text,
            exploration_anchor,
        ),
        VisualNode(
            "patch",
            "Source-code patch only",
            "output",
            exploration_section.title,
            exploration_text,
            exploration_anchor,
        ),
        VisualNode(
            "clean-run",
            "Fresh container and clean-start execution",
            "step",
            caption_section.title,
            caption,
            caption_anchor,
        ),
        VisualNode(
            "verification",
            "Up to twelve-hour verification or training",
            "step",
            verification_section.title,
            verification_text,
            verification_anchor,
        ),
        VisualNode(
            "evaluator",
            "Fixed evaluator hidden from the agent",
            "step",
            evaluator_section.title,
            evaluator_text,
            evaluator_anchor,
        ),
        VisualNode(
            "score",
            "Normalized final score",
            "output",
            scoring_section.title,
            scoring_text,
            scoring_anchor,
        ),
    ]
    return VisualSpec(
        schema_version="0.3",
        visual_type="benchmark-process",
        title="Benchmark lifecycle",
        description="The sourced path from frozen task inputs to the final score.",
        confidence="high",
        nodes=nodes,
        edges=[
            VisualEdge(nodes[index].id, nodes[index + 1].id)
            for index in range(len(nodes) - 1)
        ],
        extraction_method="deterministic-benchmark-process-v1",
    )


def build_scoring_spec(paper: Paper) -> ScoringSpec | None:
    """Extract a piecewise three-reference scoring scale when the paper states it."""

    for section in paper.sections:
        if "scor" not in section.title.lower():
            continue
        source_match = _paragraph_with_signals(
            paper,
            ("uninformative", "baseline", "optimum", "progress coordinate"),
            title_signal="scor",
        )
        branch_match = _paragraph_with_signals(
            paper, ("two branches", "0.1", "optimum"), title_signal="scor"
        )
        equation_index = next(
            (
                index
                for index, equation in enumerate(section.equations)
                if r"\begin{cases}" in equation and "0.1" in equation and "0.9" in equation
            ),
            None,
        )
        if not source_match or not branch_match or equation_index is None:
            continue
        _, source_text, source_anchor = source_match
        _, branch_text, branch_anchor = branch_match
        equation_anchor = (
            section.equation_anchors[equation_index]
            if equation_index < len(section.equation_anchors)
            else section.anchor
        )
        return ScoringSpec(
            schema_version="0.1",
            title="How the score is normalized",
            levels=[
                ScoringLevel("0", "Uninformative model"),
                ScoringLevel("0.1", "Repository's original algorithm"),
                ScoringLevel("1.0", "Task optimum"),
            ],
            explanation=(
                "After applying the task's progress coordinate, results below and above "
                "the baseline use separate linear branches."
            ),
            equation=section.equations[equation_index],
            source_section=section.title,
            source_text=f"{source_text} {branch_text}",
            source_anchor=branch_anchor or source_anchor,
            equation_anchor=equation_anchor,
        )
    return None


def build_change_layer_spec(paper: Paper) -> VisualSpec | None:
    """Extract the paper's explicit run-side versus learning-side change taxonomy."""

    match = _paragraph_with_signals(
        paper,
        (
            "four change how this run goes",
            "four change how the model learns",
            "training hyperparameters",
            "loss it optimizes",
            "update rule",
            "data",
        ),
    )
    if not match:
        return None
    section, source_text, source_anchor = match
    labels = [
        ("Run duration and saving", "execution"),
        ("Training hyperparameters", "execution"),
        ("Checkpoint selection", "execution"),
        ("Trainable capacity", "execution"),
        ("Loss or objective", "learning"),
        ("Supervision signal", "learning"),
        ("Update rule", "learning"),
        ("Training data", "learning"),
    ]
    return VisualSpec(
        schema_version="0.3",
        visual_type="change-layers",
        title="What the submissions changed",
        description="The paper's distinction between changing a run and changing learning.",
        confidence="high",
        nodes=[
            VisualNode(
                id=f"change-{index}",
                label=label,
                kind="category",
                source_section=section.title,
                source_text=source_text,
                source_anchor=source_anchor,
                group=group,
            )
            for index, (label, group) in enumerate(labels, start=1)
        ],
        edges=[],
        extraction_method="deterministic-change-layer-v1",
    )


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
        schema_version="0.3",
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
                    schema_version="0.3",
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
        schema_version="0.3",
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
        _benchmark_process_spec(paper)
        or _encoder_decoder_spec(paper)
        or _architecture_spec(paper)
        or _process_spec(paper)
        or _outline_spec(paper)
    )
    validate_visual_spec(spec)
    return spec
