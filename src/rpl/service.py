from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .comparison import empty_comparison_set
from .digest import build_digest
from .language import build_glossary
from .models import ComparisonSet, Digest, OutputQuality, Paper
from .parser import parse_arxiv_html
from .quality import apply_output_quality_rules
from .render import render_html, render_json, render_markdown
from .source import read_source
from .visual import build_visual_spec


OUTPUT_FILES = {
    "html": "paper.html",
    "markdown": "paper.md",
    "json": "paper.json",
}


@dataclass(slots=True)
class AnalysisResult:
    """Complete reusable output from one RPL paper analysis."""

    paper: Paper
    digest: Digest
    output_quality: OutputQuality
    comparison: ComparisonSet
    markdown: str
    json: str
    html: str


def safe_name(value: str) -> str:
    """Return a portable folder name derived from a paper identifier."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "paper"


def analyze_source(source: str, *, timeout: float = 30.0) -> AnalysisResult:
    """Analyze an arXiv source once for CLI, MCP, and future interfaces."""

    source_html, source_url = read_source(source, timeout=timeout)
    paper = parse_arxiv_html(source_html, source_url)
    digest = build_digest(paper)
    digest, output_quality = apply_output_quality_rules(
        paper,
        digest,
        build_visual_spec(paper),
        build_glossary(paper),
    )
    comparison = empty_comparison_set(paper)
    return AnalysisResult(
        paper=paper,
        digest=digest,
        output_quality=output_quality,
        comparison=comparison,
        markdown=render_markdown(paper, digest, output_quality),
        json=render_json(paper, digest, comparison, output_quality),
        html=render_html(paper, digest, comparison, output_quality),
    )


def write_analysis(
    analysis: AnalysisResult,
    output_root: str | Path,
    formats: tuple[str, ...] = ("markdown", "json", "html"),
) -> list[Path]:
    """Write selected analysis artifacts and return their absolute paths."""

    unknown = set(formats) - set(OUTPUT_FILES)
    if unknown:
        raise ValueError(f"Unsupported output format: {sorted(unknown)[0]}")

    destination = Path(output_root).expanduser() / safe_name(analysis.paper.paper_id)
    destination.mkdir(parents=True, exist_ok=True)
    content = {
        "html": analysis.html,
        "markdown": analysis.markdown,
        "json": analysis.json,
    }
    written: list[Path] = []
    for output_format in formats:
        path = destination / OUTPUT_FILES[output_format]
        path.write_text(content[output_format], encoding="utf-8")
        written.append(path.resolve())
    return written
