from __future__ import annotations

import re
from dataclasses import replace

from .language import reading_text
from .models import Digest, GlossaryTerm, OutputQuality, Paper, SectionQuality, VisualSpec


RESULT_SECTIONS = (
    "ablation",
    "analysis",
    "benchmark",
    "comparison",
    "evaluation",
    "experiment",
    "performance",
    "result",
)
NON_RESULT_SECTIONS = ("background", "introduction", "related work")
RESULT_SIGNALS = (
    "accuracy",
    "achieve",
    "attain",
    "better than",
    "bleu",
    "error rate",
    "establishing a new",
    "faster than",
    "improved by",
    "outperform",
    "reduced by",
    "reached",
    "score of",
    "state-of-the-art",
    "superior",
)
COMPARISON_SIGNALS = ("baseline", "compared with", "compared to", "versus", "while")
SETUP_SIGNALS = (
    "batch size",
    "beam size",
    "dataset consisting",
    "during inference",
    "learning rate",
    "maximum output length",
    "training data",
    "vocabulary",
    "we used",
)
THEORETICAL_RESULT_SIGNALS = (
    "we demonstrate",
    "we derive",
    "we establish",
    "we prove",
    "we show",
)
MEASUREMENT = re.compile(r"\b\d+(?:\.\d+)?(?:\s*%|\s*(?:bleu|x)\b)?", re.I)


def _section(
    key: str, shown: bool, item_count: int, shown_reason: str, omitted_reason: str
) -> SectionQuality:
    return SectionQuality(
        key=key,
        status="shown" if shown else "omitted",
        item_count=item_count,
        reason=shown_reason if shown else omitted_reason,
    )


def _is_reader_result(text: str, section: str, paper_type: str) -> bool:
    readable = reading_text(text).lower()
    section_name = section.lower()
    if paper_type == "theoretical":
        return any(signal in readable for signal in THEORETICAL_RESULT_SIGNALS)
    if any(signal in section_name for signal in NON_RESULT_SECTIONS):
        return False

    strong_result = any(signal in readable for signal in RESULT_SIGNALS)
    comparative = any(signal in readable for signal in COMPARISON_SIGNALS)
    result_section = any(signal in section_name for signal in RESULT_SECTIONS)
    setup = any(signal in readable for signal in SETUP_SIGNALS)
    measured = bool(MEASUREMENT.search(readable))

    if setup and not strong_result:
        return False
    abstract_result = section_name == "abstract" and comparative and measured
    return strong_result or abstract_result or (result_section and comparative and measured)


def apply_output_quality_rules(
    paper: Paper,
    digest: Digest,
    visual: VisualSpec,
    glossary: list[GlossaryTerm],
) -> tuple[Digest, OutputQuality]:
    """Return reader-approved content and an audit trail of every section decision."""

    evidence = [
        item
        for item in digest.evidence
        if _is_reader_result(item.text, item.section, digest.paper_type)
    ]
    removed_evidence = len(digest.evidence) - len(evidence)
    refined = replace(digest, evidence=evidence)

    sections = [
        _section(
            "problem",
            refined.problem is not None,
            int(refined.problem is not None),
            "A sourced problem statement was identified.",
            "No supported problem statement was identified.",
        ),
        _section(
            "core_idea",
            refined.core_idea is not None,
            int(refined.core_idea is not None),
            "A sourced core-idea statement was identified.",
            "No supported core-idea statement was identified.",
        ),
        _section(
            "visual",
            bool(visual.nodes),
            len(visual.nodes),
            "A paper visual or compact section outline is available.",
            "No safe visual structure was identified.",
        ),
        _section(
            "evidence",
            bool(refined.evidence),
            len(refined.evidence),
            "High-signal result statements passed the reader rules.",
            "No high-signal result statements passed the reader rules.",
        ),
        _section(
            "limitations",
            bool(refined.limitations),
            len(refined.limitations),
            "Explicit limitation statements were identified.",
            "No explicit limitation statements were identified.",
        ),
        _section(
            "takeaways",
            bool(refined.takeaways),
            len(refined.takeaways),
            "Discussion or conclusion statements were identified.",
            "No supported discussion or conclusion statements were identified.",
        ),
        _section(
            "glossary",
            bool(glossary),
            len(glossary),
            "Paper-defined technical terms were identified.",
            "No paper-defined technical terms were identified.",
        ),
        _section(
            "abstract",
            bool(paper.abstract.strip()),
            int(bool(paper.abstract.strip())),
            "The paper abstract is available.",
            "No abstract is available.",
        ),
    ]
    warnings = []
    if removed_evidence:
        warnings.append(
            f"Removed {removed_evidence} low-signal result candidate"
            f"{'s' if removed_evidence != 1 else ''} from the reader output."
        )
    required = {"problem", "core_idea", "evidence"}
    shown = {item.key for item in sections if item.status == "shown"}
    status = "ready" if required <= shown else "partial"
    return refined, OutputQuality(
        schema_version="0.1",
        status=status,
        sections=sections,
        warnings=warnings,
    )


def section_is_shown(quality: OutputQuality, key: str) -> bool:
    return any(item.key == key and item.status == "shown" for item in quality.sections)
