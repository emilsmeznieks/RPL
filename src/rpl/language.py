from __future__ import annotations

import re

from .models import GlossaryTerm, Paper


NUMERIC_CITATION = re.compile(r"\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
TERM_WITH_SHORT_FORM = re.compile(
    r"\b([A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,7})\s+"
    r"\(([A-Z][A-Z0-9-]{1,9})\)"
)
WORD = re.compile(r"[A-Za-z]+")
NON_TECHNICAL_EXPANSION_WORDS = {
    "journal",
    "university",
    "institute",
    "association",
}
LATEX_SYMBOLS = {
    r"\Delta": "Δ",
    r"\alpha": "α",
    r"\beta": "β",
    r"\downarrow": "↓",
    r"\infty": "∞",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pm": "±",
    r"\perp": "⊥",
    r"\phi": "φ",
    r"\prime": "′",
    r"\sigma": "σ",
    r"\times": "×",
    r"\uparrow": "↑",
    r"\varphi": "φ",
    r"\ast": "*",
}


def reading_text(text: str) -> str:
    """Remove citation clutter without rewriting the paper's words."""

    value = NUMERIC_CITATION.sub("", text)
    value = value.replace(r"\%", "%").replace(r"\,", " ")
    for command, symbol in LATEX_SYMBOLS.items():
        value = value.replace(command, symbol)
    value = re.sub(r"\\mathrm\{([^{}]+)\}", r"\1", value)
    value = re.sub(r"([A-Za-z])_\{([^{}]+)\}", r"\1 (\2)", value)
    value = re.sub(r"([A-Za-z0-9)])\^\{\\?ast\}", r"\1*", value)
    value = value.replace(r"\in", "∈").replace(r"\log", "log")
    value = value.replace(r"\{", "{").replace(r"\}", "}")
    value = re.sub(r"\\[,;:!]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _defined_term(candidate: str, short_form: str) -> str | None:
    words = list(WORD.finditer(candidate))
    target = re.sub(r"[^A-Z0-9]", "", short_form.upper())
    for start in range(len(words)):
        suffix = words[start:]
        initials = "".join(word.group(0)[0].upper() for word in suffix)
        if initials == target:
            return candidate[words[start].start() :].strip()
    return None


def build_glossary(paper: Paper, limit: int = 8) -> list[GlossaryTerm]:
    """Extract only terms that the paper defines with a parenthesized short form."""

    sources: list[tuple[str, str, str | None]] = [(paper.abstract, "Abstract", None)]
    for section in paper.sections:
        for index, paragraph in enumerate(section.paragraphs):
            anchor = (
                section.paragraph_anchors[index]
                if index < len(section.paragraph_anchors)
                else section.anchor
            )
            sources.append((paragraph, section.title, anchor))
        sources.extend(
            (figure, section.title, section.anchor) for figure in section.figures
        )

    terms: list[GlossaryTerm] = []
    seen: set[str] = set()
    for source_text, section, anchor in sources:
        for match in TERM_WITH_SHORT_FORM.finditer(source_text):
            short_form = match.group(2)
            if short_form in seen:
                continue
            term = _defined_term(match.group(1), short_form)
            if not term:
                continue
            if any(word.lower() in NON_TECHNICAL_EXPANSION_WORDS for word in term.split()):
                continue
            seen.add(short_form)
            terms.append(
                GlossaryTerm(
                    short_form=short_form,
                    term=term,
                    source_section=section,
                    source_text=source_text,
                    source_anchor=anchor,
                )
            )
            if len(terms) == limit:
                return terms
    return terms
