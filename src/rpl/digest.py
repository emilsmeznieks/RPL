from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Digest, Paper, SourcedStatement


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
NUMBER_SIGNAL = re.compile(r"(?:\b\d+(?:\.\d+)?%|\b\d{2,}\b|\$\s?\d)")

PROBLEM_SIGNALS = (
    "problem",
    "challenge",
    "limitation",
    "lack",
    "remain",
    "missing",
    "cannot",
    "fails",
    "gap",
)
IDEA_SIGNALS = (
    "this paper presents",
    "we present",
    "we propose",
    "we introduce",
    "we develop",
    "our approach",
    "our architecture",
)
EVIDENCE_SIGNALS = (
    "result",
    "outperform",
    "improv",
    "achiev",
    "significant",
    "comparison",
    "simulation",
    "accuracy",
    "reduc",
    "increase",
)
EVIDENCE_OUTCOME_SIGNALS = (
    "outperform",
    "better than",
    "zero stockout",
    "task completion",
    "service level",
    "ending cash",
    "net profit",
    "statistically",
    "significantly",
    "reduced",
    "increased",
    "achieved",
    "reached",
    "attains",
    "records no",
)
LIMITATION_SIGNALS = (
    "limitation",
    "synthetic",
    "not calibrated",
    "single-seed",
    "single seed",
    "future work",
    "cannot",
    "does not",
    "not representative",
    "generalisation",
    "generalization",
    "obstacle",
    "barrier",
)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_BOUNDARY.split(text) if len(part.strip()) >= 35]


def _statement(text: str, section: str) -> SourcedStatement:
    return SourcedStatement(text=text, section=section)


def _first_matching(
    items: Iterable[tuple[str, str]], signals: tuple[str, ...]
) -> SourcedStatement | None:
    for text, section in items:
        lowered = text.lower()
        if any(signal in lowered for signal in signals):
            return _statement(text, section)
    return None


def _unique(items: Iterable[SourcedStatement], limit: int) -> list[SourcedStatement]:
    result: list[SourcedStatement] = []
    seen: set[str] = set()
    for item in items:
        key = re.sub(r"\W+", " ", item.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) == limit:
            break
    return result


def _ranked_unique(
    items: Iterable[tuple[int, int, SourcedStatement]], limit: int
) -> list[SourcedStatement]:
    ranked = sorted(items, key=lambda item: (-item[0], item[1]))
    return _unique((item[2] for item in ranked), limit)


def build_digest(paper: Paper) -> Digest:
    """Build a conservative extractive digest without inventing new claims."""

    abstract_sentences = [(text, "Abstract") for text in sentences(paper.abstract)]
    all_section_sentences: list[tuple[str, str]] = []
    for section in paper.sections:
        for paragraph in section.paragraphs:
            all_section_sentences.extend(
                (text, section.title) for text in sentences(paragraph)
            )

    problem = _first_matching(abstract_sentences, PROBLEM_SIGNALS)
    if problem is None and abstract_sentences:
        problem = _statement(*abstract_sentences[0])

    core_idea = _first_matching(abstract_sentences, IDEA_SIGNALS)
    if core_idea is None and len(abstract_sentences) > 1:
        core_idea = _statement(*abstract_sentences[1])

    evidence_candidates: list[tuple[int, int, SourcedStatement]] = []
    for order, (text, section) in enumerate(abstract_sentences + all_section_sentences):
        lowered = text.lower()
        section_lower = section.lower()
        result_section = any(token in section_lower for token in ("result", "performance", "comparison", "ablation", "discussion"))
        outcome = any(token in lowered for token in EVIDENCE_OUTCOME_SIGNALS)
        general_signal = any(token in lowered for token in EVIDENCE_SIGNALS)
        has_number = bool(NUMBER_SIGNAL.search(text))
        if has_number and (result_section or outcome):
            score = (5 if result_section else 0) + (4 if outcome else 0) + (1 if general_signal else 0)
            evidence_candidates.append((score, order, _statement(text, section)))

    limitation_candidates: list[tuple[int, int, SourcedStatement]] = []
    for order, (text, section) in enumerate(all_section_sentences):
        lowered = text.lower()
        section_lower = section.lower()
        signal_count = sum(signal in lowered for signal in LIMITATION_SIGNALS)
        limitation_section = "limitation" in section_lower
        discussion_section = "discussion" in section_lower or "conclusion" in section_lower
        is_outcome = any(token in lowered for token in EVIDENCE_OUTCOME_SIGNALS)
        if "baseline cannot" in lowered:
            continue
        if signal_count == 1 and is_outcome and not limitation_section:
            continue
        if signal_count and (limitation_section or discussion_section or signal_count >= 2):
            score = (7 if limitation_section else 0) + (3 if discussion_section else 0) + signal_count
            limitation_candidates.append((score, order, _statement(text, section)))

    takeaway_candidates: list[SourcedStatement] = []
    for text, section in all_section_sentences:
        section_lower = section.lower()
        if any(token in section_lower for token in ("conclusion", "discussion")):
            takeaway_candidates.append(_statement(text, section))

    return Digest(
        problem=problem,
        core_idea=core_idea,
        evidence=_ranked_unique(evidence_candidates, 5),
        limitations=_ranked_unique(limitation_candidates, 5),
        takeaways=_unique(takeaway_candidates, 3),
    )
