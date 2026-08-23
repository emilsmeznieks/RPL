from __future__ import annotations

import re
import ssl
import threading
import time
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import certifi

from .comparison import COMPARISON_SCHEMA_VERSION, validate_comparison_set
from .digest import build_digest
from .models import (
    ComparisonDimension,
    ComparisonEvidence,
    ComparisonSet,
    ComparisonValue,
    Digest,
    Paper,
    RelatedPaper,
    RelationSignal,
)
from .source import arxiv_id


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_API_INTERVAL_SECONDS = 3.0
ATOM = "{http://www.w3.org/2005/Atom}"
WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
VERSION_SUFFIX = re.compile(r"v\d+$", re.I)
STOP_WORDS = {
    "about",
    "after",
    "also",
    "among",
    "based",
    "best",
    "between",
    "could",
    "from",
    "have",
    "into",
    "model",
    "models",
    "more",
    "need",
    "new",
    "network",
    "paper",
    "propose",
    "proposed",
    "results",
    "show",
    "simple",
    "solely",
    "system",
    "their",
    "these",
    "this",
    "through",
    "using",
    "were",
    "which",
    "with",
}
_API_LOCK = threading.Lock()
_LAST_API_REQUEST = 0.0


class DiscoveryError(RuntimeError):
    """Raised when arXiv metadata discovery cannot be completed safely."""


@dataclass(slots=True)
class ArxivCandidate:
    paper_id: str
    title: str
    authors: list[str]
    published: str | None
    abstract: str
    categories: list[str]


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _base_id(value: str) -> str:
    return VERSION_SUFFIX.sub("", value).lower()


def _tokens(value: str) -> list[str]:
    return [
        token.lower()
        for token in WORD.findall(value)
        if len(token) >= 4 and token.lower() not in STOP_WORDS
    ]


def search_terms(
    paper: Paper, focus_text: str | None = None, limit: int = 5
) -> list[str]:
    """Choose a small deterministic query from the paper's own words."""

    title_tokens = _tokens(paper.title)
    focus_tokens = _tokens(focus_text or paper.abstract)
    focus_counts = Counter(focus_tokens)
    first_position: dict[str, int] = {}
    for index, token in enumerate(focus_tokens):
        first_position.setdefault(token, index)
    ordered: list[str] = []
    for token in title_tokens:
        if token not in ordered:
            ordered.append(token)
    for token, _ in sorted(
        focus_counts.items(),
        key=lambda item: (-item[1], first_position[item[0]]),
    ):
        if token not in ordered:
            ordered.append(token)
    return ordered[:limit]


def build_discovery_url(
    paper: Paper, focus_text: str | None = None, result_pool: int = 20
) -> str:
    terms = search_terms(paper, focus_text)
    if not terms:
        raise DiscoveryError("The paper does not contain enough text for discovery.")
    query = " OR ".join(f'all:"{term}"' for term in terms)
    parameters = {
        "search_query": query,
        "start": 0,
        "max_results": result_pool,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def parse_arxiv_feed(value: str) -> list[ArxivCandidate]:
    """Parse the documented Atom fields returned by the arXiv API."""

    try:
        root = ElementTree.fromstring(value)
    except ElementTree.ParseError as exc:
        raise DiscoveryError("arXiv returned invalid metadata XML.") from exc

    candidates: list[ArxivCandidate] = []
    for entry in root.findall(f"{ATOM}entry"):
        identifier = _clean(entry.findtext(f"{ATOM}id"))
        if "/api/errors#" in identifier:
            message = _clean(entry.findtext(f"{ATOM}summary"))
            raise DiscoveryError(message or "arXiv rejected the discovery query.")
        paper_id = arxiv_id(identifier)
        title = _clean(entry.findtext(f"{ATOM}title"))
        abstract = _clean(entry.findtext(f"{ATOM}summary"))
        if not paper_id or not title or not abstract:
            continue
        authors = [
            name
            for author in entry.findall(f"{ATOM}author")
            if (name := _clean(author.findtext(f"{ATOM}name")))
        ]
        published = _clean(entry.findtext(f"{ATOM}published")) or None
        categories = [
            term
            for category in entry.findall(f"{ATOM}category")
            if (term := _clean(category.get("term")))
        ]
        candidates.append(
            ArxivCandidate(
                paper_id=paper_id,
                title=title,
                authors=authors,
                published=published[:10] if published else None,
                abstract=abstract,
                categories=categories,
            )
        )
    return candidates


def fetch_arxiv_candidates(
    paper: Paper,
    *,
    focus_text: str | None = None,
    timeout: float = 30.0,
    result_pool: int = 20,
) -> list[ArxivCandidate]:
    url = build_discovery_url(
        paper, focus_text=focus_text, result_pool=result_pool
    )
    request = Request(
        url,
        headers={
            "User-Agent": "RPL/0.9 (+https://github.com/emilsmeznieks/RPL)",
            "Accept": "application/atom+xml,application/xml",
        },
    )
    global _LAST_API_REQUEST
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with _API_LOCK:
            wait = ARXIV_API_INTERVAL_SECONDS - (time.monotonic() - _LAST_API_REQUEST)
            if wait > 0:
                time.sleep(wait)
            _LAST_API_REQUEST = time.monotonic()
            with urlopen(request, timeout=timeout, context=context) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
        return parse_arxiv_feed(body)
    except OSError as exc:
        raise DiscoveryError(f"Could not query arXiv metadata: {exc}") from exc


def _sentences(value: str) -> list[str]:
    return [item.strip() for item in SENTENCE_BOUNDARY.split(value) if item.strip()]


def _best_evidence(value: str, shared: set[str]) -> str:
    sentences = _sentences(value)
    return max(
        sentences,
        key=lambda sentence: (len(set(_tokens(sentence)) & shared), -len(sentence)),
        default=value.strip(),
    )


def _best_relation_evidence(
    title: str, abstract: str, shared: set[str]
) -> tuple[str, str]:
    options = [("Title", title)] + [
        ("Abstract", item) for item in _sentences(abstract)
    ]
    return max(
        options,
        key=lambda item: (
            len(set(_tokens(item[1])) & shared),
            int(item[0] == "Title"),
            -len(item[1]),
        ),
    )


def _candidate_focus(candidate: ArxivCandidate, shared: set[str]) -> str:
    candidate_paper = Paper(
        paper_id=candidate.paper_id,
        title=candidate.title,
        authors=candidate.authors,
        published=candidate.published,
        source_url=f"https://arxiv.org/abs/{candidate.paper_id}",
        abstract=candidate.abstract,
    )
    digest = build_digest(candidate_paper)
    if digest.core_idea is not None:
        return digest.core_idea.text
    return _best_evidence(candidate.abstract, shared)


def _ranked_candidates(
    paper: Paper, candidates: list[ArxivCandidate], focus_text: str | None = None
) -> list[tuple[int, set[str], ArxivCandidate]]:
    focal_tokens = set(_tokens(f"{paper.title} {focus_text or paper.abstract}"))
    focal_title = set(_tokens(paper.title))
    ranked: list[tuple[int, set[str], ArxivCandidate]] = []
    for candidate in candidates:
        if _base_id(candidate.paper_id) == _base_id(paper.paper_id):
            continue
        candidate_tokens = set(_tokens(f"{candidate.title} {candidate.abstract}"))
        shared = focal_tokens & candidate_tokens
        candidate_title = set(_tokens(candidate.title))
        direct_title_overlap = focal_title & candidate_title
        if len(shared) < 3 and not direct_title_overlap:
            continue
        title_overlap = focal_title & candidate_tokens
        candidate_title_overlap = candidate_title & focal_tokens
        _, focal_evidence = _best_relation_evidence(
            paper.title, paper.abstract, shared
        )
        _, candidate_evidence = _best_relation_evidence(
            candidate.title, candidate.abstract, shared
        )
        if min(
            len(set(_tokens(focal_evidence)) & shared),
            len(set(_tokens(candidate_evidence)) & shared),
        ) < 2:
            continue
        score = (
            len(shared)
            + (3 * len(title_overlap))
            + (2 * len(candidate_title_overlap))
        )
        ranked.append((score, shared, candidate))
    return sorted(
        ranked,
        key=lambda item: (item[0], item[2].published or "", item[2].paper_id),
        reverse=True,
    )


def discover_related_papers(
    paper: Paper,
    digest: Digest,
    *,
    timeout: float = 30.0,
    limit: int = 3,
    candidates: list[ArxivCandidate] | None = None,
) -> ComparisonSet:
    """Find and compare related papers using only sourced arXiv metadata."""

    focus_text = digest.core_idea.text if digest.core_idea is not None else paper.abstract
    pool = candidates if candidates is not None else fetch_arxiv_candidates(
        paper, focus_text=focus_text, timeout=timeout
    )
    ranked = _ranked_candidates(paper, pool, focus_text=focus_text)[:limit]
    method = "arxiv-api-relevance-and-abstract-overlap-v1"
    if not ranked:
        spec = ComparisonSet(
            schema_version=COMPARISON_SCHEMA_VERSION,
            focal_paper_id=paper.paper_id,
            status="no-match",
            related_papers=[],
            relation_signals=[],
            dimensions=[],
            discovery_method=method,
            generated_claims=False,
        )
        validate_comparison_set(spec)
        return spec

    related: list[RelatedPaper] = []
    signals: list[RelationSignal] = []
    focus_values: list[ComparisonValue] = []
    focal_shared: set[str] = set()
    for score, shared, candidate in ranked:
        focal_section, focal_text = _best_relation_evidence(
            paper.title, paper.abstract, shared
        )
        candidate_section, candidate_text = _best_relation_evidence(
            candidate.title, candidate.abstract, shared
        )
        candidate_focus = _candidate_focus(candidate, shared)
        related.append(
            RelatedPaper(
                paper_id=candidate.paper_id,
                title=candidate.title,
                authors=candidate.authors,
                published=candidate.published,
                source_url=f"https://arxiv.org/abs/{candidate.paper_id}",
            )
        )
        signals.append(
            RelationSignal(
                related_paper_id=candidate.paper_id,
                kind="same-topic",
                confidence="high" if score >= 16 and len(shared) >= 5 else "moderate",
                evidence=[
                    ComparisonEvidence(
                        paper_id=paper.paper_id,
                        text=focal_text,
                        section=focal_section,
                    ),
                    ComparisonEvidence(
                        paper_id=candidate.paper_id,
                        text=candidate_text,
                        section=candidate_section,
                    ),
                ],
            )
        )
        focal_shared.update(shared)
        focus_values.append(
            ComparisonValue(
                paper_id=candidate.paper_id,
                text=candidate_focus,
                section="Abstract",
            )
        )

    focal_focus = (
        digest.core_idea.text
        if digest.core_idea is not None and digest.core_idea.section == "Abstract"
        else _best_evidence(paper.abstract, focal_shared)
    )
    dimension = ComparisonDimension(
        key="abstract-focus",
        label="Abstract focus",
        values=[
            ComparisonValue(
                paper_id=paper.paper_id,
                text=focal_focus,
                section="Abstract",
                source_anchor=(
                    digest.core_idea.source_anchor
                    if digest.core_idea is not None
                    and digest.core_idea.section == "Abstract"
                    else None
                ),
            ),
            *focus_values,
        ],
    )
    spec = ComparisonSet(
        schema_version=COMPARISON_SCHEMA_VERSION,
        focal_paper_id=paper.paper_id,
        status="complete",
        related_papers=related,
        relation_signals=signals,
        dimensions=[dimension],
        discovery_method=method,
        generated_claims=False,
    )
    validate_comparison_set(spec)
    return spec
