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
PROBLEM_STRONG_SIGNALS = (
    "bottleneck",
    "cannot",
    "constraint",
    "drawback",
    "fails",
    "gap",
    "lack",
    "limitation",
    "limited by",
    "preclude",
    "prevent",
    "problem",
    "unable",
)
PROBLEM_CONSEQUENCE_SIGNALS = (
    "critical",
    "difficult",
    "expensive",
    "memory",
    "parallel",
    "scalability",
    "slow",
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
LOW_INFORMATION_SIGNALS = (
    "supports three principal findings",
    "the following observations",
    "this section discusses",
    "we discuss",
    "is organised as follows",
    "is organized as follows",
)
EMPIRICAL_PAPER_SIGNALS = (
    "ablation",
    "accuracy",
    "benchmark",
    "dataset",
    "empirical",
    "evaluation",
    "experiment",
    "performance",
    "result",
    "simulation",
)
THEORETICAL_PAPER_SIGNALS = (
    "analytical",
    "corollary",
    "correspondence",
    "derivation",
    "formalism",
    "invariant",
    "lemma",
    "proof",
    "proposition",
    "spectrum",
    "theorem",
)
THEORETICAL_STRONG_RESULT_SIGNALS = (
    "correspondence between",
    "is equivalent to",
    "we demonstrate",
    "we derive",
    "we establish",
    "we explicitly give",
    "we have derived",
    "we have established",
    "we have shown",
    "we prove",
    "we show",
)
THEORETICAL_WEAK_RESULT_SIGNALS = (
    "we construct",
    "we find",
    "we obtain",
)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_BOUNDARY.split(text) if len(part.strip()) >= 35]


def _statement(
    text: str,
    section: str,
    section_anchor: str | None = None,
    source_anchor: str | None = None,
) -> SourcedStatement:
    return SourcedStatement(
        text=text,
        section=section,
        section_anchor=section_anchor,
        source_anchor=source_anchor,
    )


def _first_matching(
    items: Iterable[tuple[str, str, str | None, str | None]], signals: tuple[str, ...]
) -> SourcedStatement | None:
    for text, section, section_anchor, source_anchor in items:
        lowered = text.lower()
        if any(signal in lowered for signal in signals):
            return _statement(text, section, section_anchor, source_anchor)
    return None


def _problem_statement(
    items: Iterable[tuple[str, str, str | None, str | None]],
) -> SourcedStatement | None:
    """Select an explicit constraint or research gap instead of background text."""

    candidates: list[tuple[int, int, SourcedStatement]] = []
    for order, (text, section, section_anchor, source_anchor) in enumerate(items):
        lowered = text.lower()
        strong_count = sum(signal in lowered for signal in PROBLEM_STRONG_SIGNALS)
        weak_count = sum(signal in lowered for signal in PROBLEM_SIGNALS)
        consequence_count = sum(
            signal in lowered for signal in PROBLEM_CONSEQUENCE_SIGNALS
        )
        if not strong_count:
            continue
        section_score = 3 if "introduction" in section.lower() else 2
        idea_penalty = 6 if any(signal in lowered for signal in IDEA_SIGNALS) else 0
        question_penalty = 3 if "?" in text else 0
        score = (
            section_score
            + (5 * strong_count)
            + (2 * weak_count)
            + consequence_count
            - idea_penalty
            - question_penalty
        )
        if score >= 7:
            candidates.append(
                (
                    score,
                    order,
                    _statement(text, section, section_anchor, source_anchor),
                )
            )
    return _ranked_unique(candidates, 1)[0] if candidates else None


def _text_key(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _unique(
    items: Iterable[SourcedStatement],
    limit: int,
    excluded: Iterable[SourcedStatement | None] = (),
) -> list[SourcedStatement]:
    result: list[SourcedStatement] = []
    seen_text = {_text_key(item.text) for item in excluded if item is not None}
    seen_paragraphs: set[tuple[str, str]] = set()
    for item in items:
        text_key = _text_key(item.text)
        paragraph_key = None
        if item.source_anchor and item.source_anchor != item.section_anchor:
            paragraph_key = (item.section, item.source_anchor)
        if text_key in seen_text or (
            paragraph_key is not None and paragraph_key in seen_paragraphs
        ):
            continue
        seen_text.add(text_key)
        if paragraph_key is not None:
            seen_paragraphs.add(paragraph_key)
        result.append(item)
        if len(result) == limit:
            break
    return result


def _ranked_unique(
    items: Iterable[tuple[int, int, SourcedStatement]],
    limit: int,
    excluded: Iterable[SourcedStatement | None] = (),
) -> list[SourcedStatement]:
    ranked = sorted(items, key=lambda item: (-item[0], item[1]))
    return _unique((item[2] for item in ranked), limit, excluded)


def classify_paper(paper: Paper) -> tuple[str, str]:
    """Classify broad paper type from explicit structural and language signals."""

    profile_text = " ".join(
        [paper.abstract, *(section.title for section in paper.sections)]
    ).lower()
    empirical_score = sum(signal in profile_text for signal in EMPIRICAL_PAPER_SIGNALS)
    theoretical_score = sum(
        signal in profile_text for signal in THEORETICAL_PAPER_SIGNALS
    )

    paragraph_count = sum(len(section.paragraphs) for section in paper.sections)
    equation_count = sum(len(section.equations) for section in paper.sections)
    if paragraph_count and equation_count >= paragraph_count * 2:
        theoretical_score += 2

    difference = empirical_score - theoretical_score
    if empirical_score >= 2 and difference >= 2:
        return "empirical", "high" if difference >= 4 else "moderate"
    if theoretical_score >= 2 and difference <= -2:
        return "theoretical", "high" if difference <= -4 else "moderate"
    return "unknown", "low"


def build_digest(paper: Paper) -> Digest:
    """Build a conservative extractive digest without inventing new claims."""

    abstract_sentences = [
        (text, "Abstract", None, None) for text in sentences(paper.abstract)
    ]
    all_section_sentences: list[tuple[str, str, str | None, str | None]] = []
    for section in paper.sections:
        for index, paragraph in enumerate(section.paragraphs):
            source_anchor = (
                section.paragraph_anchors[index]
                if index < len(section.paragraph_anchors)
                else section.anchor
            )
            all_section_sentences.extend(
                (text, section.title, section.anchor, source_anchor)
                for text in sentences(paragraph)
            )

    paper_type, paper_type_confidence = classify_paper(paper)
    introduction_sentences = [
        item
        for item in all_section_sentences
        if "introduction" in item[1].lower()
    ]

    problem = _problem_statement(abstract_sentences + introduction_sentences)

    core_idea = _first_matching(abstract_sentences, IDEA_SIGNALS)
    if core_idea is None and paper_type == "theoretical" and abstract_sentences:
        core_idea = _statement(*abstract_sentences[0])
    elif core_idea is None and len(abstract_sentences) > 1:
        core_idea = _statement(*abstract_sentences[1])

    evidence_candidates: list[tuple[int, int, SourcedStatement]] = []
    for order, (text, section, section_anchor, source_anchor) in enumerate(
        abstract_sentences + all_section_sentences
    ):
        lowered = text.lower()
        section_lower = section.lower()
        result_section = any(token in section_lower for token in ("result", "performance", "comparison", "ablation", "discussion"))
        outcome = any(token in lowered for token in EVIDENCE_OUTCOME_SIGNALS)
        general_signal = any(token in lowered for token in EVIDENCE_SIGNALS)
        has_number = bool(NUMBER_SIGNAL.search(text))
        theoretical_strong_count = sum(
            signal in lowered for signal in THEORETICAL_STRONG_RESULT_SIGNALS
        )
        theoretical_weak_count = sum(
            signal in lowered for signal in THEORETICAL_WEAK_RESULT_SIGNALS
        )
        theoretical_section = any(
            token in section_lower
            for token in (
                "analysis",
                "conclusion",
                "correspondence",
                "derivation",
                "proof",
                "result",
                "spectrum",
                "theorem",
            )
        )
        strong_theoretical_section = any(
            token in section_lower
            for token in ("conclusion", "proof", "result", "theorem")
        )
        if (
            paper_type == "theoretical"
            and "?" not in text
            and (section == "Abstract" or theoretical_section)
            and (
                theoretical_strong_count
                or (strong_theoretical_section and theoretical_weak_count)
            )
        ):
            score = (
                (8 if "conclusion" in section_lower else 0)
                + (6 if section == "Abstract" else 0)
                + (5 if strong_theoretical_section else 0)
                + (2 if theoretical_section else 0)
                + (4 * theoretical_strong_count)
                + theoretical_weak_count
            )
            evidence_candidates.append(
                (
                    score,
                    order,
                    _statement(text, section, section_anchor, source_anchor),
                )
            )
        elif (
            paper_type != "theoretical"
            and has_number
            and (result_section or outcome)
        ):
            score = (
                (5 if result_section else 0)
                + (4 if outcome else 0)
                + (1 if general_signal else 0)
            )
            evidence_candidates.append(
                (
                    score,
                    order,
                    _statement(text, section, section_anchor, source_anchor),
                )
            )

    limitation_candidates: list[tuple[int, int, SourcedStatement]] = []
    for order, (text, section, section_anchor, source_anchor) in enumerate(
        all_section_sentences
    ):
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
            score = (
                (7 if limitation_section else 0)
                + (3 if discussion_section else 0)
                + signal_count
            )
            limitation_candidates.append(
                (
                    score,
                    order,
                    _statement(text, section, section_anchor, source_anchor),
                )
            )

    conclusion_candidates: list[SourcedStatement] = []
    discussion_candidates: list[SourcedStatement] = []
    for text, section, section_anchor, source_anchor in all_section_sentences:
        section_lower = section.lower()
        text_lower = text.lower()
        if any(signal in text_lower for signal in LOW_INFORMATION_SIGNALS):
            continue
        if "conclusion" in section_lower:
            conclusion_candidates.append(
                _statement(text, section, section_anchor, source_anchor)
            )
        elif "discussion" in section_lower and not any(
            signal in text_lower for signal in LIMITATION_SIGNALS
        ):
            discussion_candidates.append(
                _statement(text, section, section_anchor, source_anchor)
            )

    evidence = _ranked_unique(
        evidence_candidates, 5, excluded=(problem, core_idea)
    )
    takeaway_candidates = discussion_candidates
    if paper_type != "theoretical":
        takeaway_candidates = conclusion_candidates + discussion_candidates
    return Digest(
        problem=problem,
        core_idea=core_idea,
        evidence=evidence,
        limitations=_ranked_unique(limitation_candidates, 5),
        takeaways=_unique(takeaway_candidates, 3, excluded=evidence),
        paper_type=paper_type,
        paper_type_confidence=paper_type_confidence,
    )
