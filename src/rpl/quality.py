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
    "average",
    "achieve",
    "attain",
    "better than",
    "bleu",
    "error rate",
    "establishing a new",
    "faster than",
    "improved by",
    "mean score",
    "outperform",
    "reduced by",
    "reached",
    "reaches",
    "rises from",
    "share of submissions",
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
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")
TABLE_HEADERS = (
    "accuracy",
    "average",
    "baseline",
    "configuration",
    "cost",
    "effort",
    "harness",
    "metric",
    "model",
    "score",
    "system",
)
TABLE_CONTROL_TOKENS = (r"\uparrow", r"\downarrow", r"\ast", r"\perp", r"\infty")


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


def evidence_rejection_reason(text: str) -> str | None:
    """Reject content whose shape is unsafe or unusable as reader evidence."""

    stripped = text.strip()
    if len(stripped) > 700 or len(stripped.split()) > 120:
        return "excessively-long"

    numbers = NUMBER_TOKEN.findall(stripped)
    words = re.findall(r"[A-Za-z][A-Za-z0-9.-]*", stripped)
    token_count = max(1, len(numbers) + len(words))
    numeric_density = len(numbers) / token_count
    header_count = sum(header in stripped.lower() for header in TABLE_HEADERS)
    control_count = sum(token in stripped for token in TABLE_CONTROL_TOKENS)
    sentence_marks = sum(stripped.count(mark) for mark in ".?!")

    if len(numbers) >= 18 and numeric_density >= 0.18:
        return "table-like"
    if len(stripped) > 280 and len(numbers) >= 8 and header_count >= 3:
        return "table-like"
    if len(stripped) > 400 and len(numbers) >= 10 and sentence_marks <= 1:
        return "table-like"
    if len(numbers) >= 8 and control_count >= 2:
        return "table-like"
    return None


def apply_output_quality_rules(
    paper: Paper,
    digest: Digest,
    visual: VisualSpec,
    glossary: list[GlossaryTerm],
) -> tuple[Digest, OutputQuality]:
    """Return reader-approved content and an audit trail of every section decision."""

    evidence = []
    table_like_removed = 0
    excessively_long_removed = 0
    low_signal_removed = 0
    for item in digest.evidence:
        rejection = evidence_rejection_reason(item.text)
        if rejection == "table-like":
            table_like_removed += 1
        elif rejection == "excessively-long":
            excessively_long_removed += 1
        elif _is_reader_result(item.text, item.section, digest.paper_type):
            evidence.append(item)
        else:
            low_signal_removed += 1
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
            (
                "A sourced substantive paper visual is available."
                if visual.visual_type != "paper-outline"
                else "A low-confidence section-outline fallback is available."
            ),
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
    warnings = list(paper.extraction_warnings)
    if table_like_removed:
        warnings.append(
            f"Rejected {table_like_removed} table-like evidence candidate"
            f"{'s' if table_like_removed != 1 else ''}."
        )
    if excessively_long_removed:
        warnings.append(
            f"Rejected {excessively_long_removed} excessively long evidence candidate"
            f"{'s' if excessively_long_removed != 1 else ''}."
        )
    if low_signal_removed:
        warnings.append(
            f"Removed {low_signal_removed} low-signal result candidate"
            f"{'s' if low_signal_removed != 1 else ''} from the reader output."
        )
    substantive_visual = visual.visual_type != "paper-outline" and visual.confidence != "low"
    if not substantive_visual:
        warnings.append("Used a low-confidence paper-outline visual fallback.")
    if not refined.limitations:
        warnings.append("No explicit limitations were identified in the paper text.")
    required = {"problem", "core_idea", "evidence"}
    shown = {item.key for item in sections if item.status == "shown"}
    ready = required <= shown and substantive_visual and bool(refined.limitations)
    status = "ready" if ready else "partial"
    return refined, OutputQuality(
        schema_version="0.2",
        status=status,
        sections=sections,
        warnings=warnings,
        method="deterministic-output-quality-v2",
    )


def section_is_shown(quality: OutputQuality, key: str) -> bool:
    return any(item.key == key and item.status == "shown" for item in quality.sections)
