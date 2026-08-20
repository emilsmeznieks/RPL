from __future__ import annotations

import json
import re
from html import escape
from typing import Any
from urllib.parse import quote, urlparse

from .comparison import empty_comparison_set, validate_comparison_set
from .language import build_glossary, reading_text
from .models import (
    ComparisonSet,
    Digest,
    GlossaryTerm,
    OutputQuality,
    Paper,
    SourcedStatement,
    VisualSpec,
)
from .quality import apply_output_quality_rules, section_is_shown
from .visual import build_visual_spec


def _source_href(source_url: str, anchor: str | None) -> str | None:
    base = source_url.split("#", 1)[0]
    return f"{base}#{quote(anchor, safe='')}" if anchor else base


def _markdown_source(
    source_url: str, section: str, anchor: str | None
) -> str:
    href = _source_href(source_url, anchor)
    return f"[{section}]({href})" if href else section


def _statement_anchor(item: SourcedStatement) -> str | None:
    return item.source_anchor or item.section_anchor


def _markdown_statement(paper: Paper, item: SourcedStatement | None) -> str:
    if item is None:
        return "RPL could not identify this clearly from the paper."
    source = _markdown_source(paper.source_url, item.section, _statement_anchor(item))
    return f"{reading_text(item.text)}\n\n_Source: {source}_"


def _markdown_list(
    paper: Paper, items: list[SourcedStatement], empty_text: str = "No matching statements found."
) -> str:
    if not items:
        return f"- {empty_text}"
    lines = []
    for item in items:
        source = _markdown_source(
            paper.source_url, item.section, _statement_anchor(item)
        )
        lines.append(f"- {reading_text(item.text)} _(Source: {source})_")
    return "\n".join(lines)


def _markdown_glossary(paper: Paper, terms: list[GlossaryTerm]) -> str:
    if not terms:
        return ""
    lines = ["## Terms used in the paper", ""]
    for term in terms:
        source = _markdown_source(
            paper.source_url, term.source_section, term.source_anchor
        )
        lines.append(f"- **{term.short_form}:** {term.term} _(Source: {source})_")
    return "\n".join(lines) + "\n\n"


def _results_heading(digest: Digest) -> str:
    if digest.paper_type == "theoretical":
        return "Main theoretical results stated in the paper"
    return "Results reported in the paper"


def _node_label(value: str, maximum: int = 42) -> str:
    value = re.sub(r"[^\w\s-]", "", value).strip()
    return value if len(value) <= maximum else value[: maximum - 1].rstrip() + "…"


def outline_mermaid(paper: Paper) -> str:
    major = [section for section in paper.sections if section.level == 2][:6]
    if not major:
        return "flowchart LR\n  A[Paper] --> B[No section outline extracted]"
    lines = ["flowchart LR", '  P["Paper"]']
    previous = "P"
    for index, section in enumerate(major, start=1):
        node = f"S{index}"
        lines.append(f'  {previous} --> {node}["{_node_label(section.title)}"]')
        previous = node
    return "\n".join(lines)


def render_markdown(
    paper: Paper, digest: Digest, output_quality: OutputQuality | None = None
) -> str:
    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    glossary = build_glossary(paper)
    visual = build_visual_spec(paper)
    if output_quality is None:
        digest, output_quality = apply_output_quality_rules(
            paper, digest, visual, glossary
        )
    sections = [f"""# {paper.title}

> RPL paper guide · [{paper.paper_id}]({paper.source_url})

**Authors:** {authors}  
**Published:** {paper.published or "Unknown"}  
**Keywords:** {keywords}
"""]
    if section_is_shown(output_quality, "problem"):
        sections.append(f"""## The problem

{_markdown_statement(paper, digest.problem)}
""")
    if section_is_shown(output_quality, "core_idea"):
        sections.append(f"""## The core idea

{_markdown_statement(paper, digest.core_idea)}
""")
    if section_is_shown(output_quality, "evidence"):
        sections.append(f"""## {_results_heading(digest)}

{_markdown_list(paper, digest.evidence)}
""")
    if section_is_shown(output_quality, "limitations"):
        sections.append(f"""## Limitations

{_markdown_list(paper, digest.limitations)}
""")
    if section_is_shown(output_quality, "takeaways"):
        sections.append(f"""## Key points from the discussion

{_markdown_list(paper, digest.takeaways)}
""")
    if section_is_shown(output_quality, "glossary"):
        sections.append(_markdown_glossary(paper, glossary))
    sections.append(f"""## Paper map

```mermaid
{outline_mermaid(paper)}
```
""")
    if section_is_shown(output_quality, "abstract"):
        sections.append(f"""## Abstract

{reading_text(paper.abstract) or "No abstract extracted."}
""")
    return "\n".join(section.strip() for section in sections if section.strip()) + "\n"


def knowledge_payload(
    paper: Paper,
    digest: Digest,
    comparison: ComparisonSet | None = None,
    output_quality: OutputQuality | None = None,
) -> dict[str, Any]:
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    if output_quality is None:
        digest, output_quality = apply_output_quality_rules(
            paper, digest, visual, glossary
        )
    comparison = comparison or empty_comparison_set(paper)
    if comparison.focal_paper_id != paper.paper_id:
        raise ValueError("The comparison focal paper must match the rendered paper.")
    validate_comparison_set(comparison)
    return {
        "schema_version": "0.8",
        "paper": paper.to_dict(),
        "digest": digest.to_dict(),
        "visual": visual.to_dict(),
        "glossary": [term.to_dict() for term in glossary],
        "output_quality": output_quality.to_dict(),
        "comparison": comparison.to_dict(),
        "provenance": {
            "source_url": paper.source_url,
            "extraction_method": digest.extraction_method,
            "generated_claims": False,
        },
    }


def render_json(
    paper: Paper,
    digest: Digest,
    comparison: ComparisonSet | None = None,
    output_quality: OutputQuality | None = None,
) -> str:
    return json.dumps(
        knowledge_payload(paper, digest, comparison, output_quality),
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def _safe_href(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"https", "http", "file"}:
        return escape(value, quote=True)
    return "#"


def _html_source(
    source_url: str, section: str, anchor: str | None, class_name: str
) -> str:
    href = _source_href(source_url, anchor)
    label = escape(section)
    if href:
        label = f'<a href="{_safe_href(href)}">{label}</a>'
    return f'<p class="{class_name}">Source: {label}</p>'


def _html_statement(paper: Paper, item: SourcedStatement | None) -> str:
    if item is None:
        return '<p class="muted">RPL could not identify this clearly from the paper.</p>'
    source = _html_source(
        paper.source_url, item.section, _statement_anchor(item), "source-label"
    )
    return (
        f"<p>{escape(reading_text(item.text))}</p>"
        f"{source}"
    )


def _html_list(
    paper: Paper, items: list[SourcedStatement], empty_text: str = "No matching statements found."
) -> str:
    if not items:
        return f'<p class="muted">{escape(empty_text)}</p>'
    cards = []
    for item in items:
        source = _html_source(
            paper.source_url, item.section, _statement_anchor(item), "source-label"
        )
        cards.append(
            '<li class="statement">'
            f"<p>{escape(reading_text(item.text))}</p>"
            f"{source}"
            "</li>"
        )
    return f'<ul class="statement-list">{"".join(cards)}</ul>'


def _html_paper_map(paper: Paper) -> str:
    major = [section for section in paper.sections if section.level == 2][:6]
    if not major:
        return '<p class="muted">No section outline extracted.</p>'
    nodes = []
    for index, section in enumerate(major, start=1):
        nodes.append(
            '<li class="map-node">'
            f'<span class="map-number">{index:02d}</span>'
            f"<span>{escape(section.title)}</span>"
            "</li>"
        )
    return f'<ol class="paper-map">{"".join(nodes)}</ol>'


def _html_abstract(text: str) -> str:
    readable = reading_text(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", readable)
    paragraphs = [part.strip() for part in parts if part.strip()]
    if not paragraphs:
        return '<p class="muted">No abstract extracted.</p>'
    return '<div class="abstract-text">' + "".join(
        f"<p>{escape(part)}</p>" for part in paragraphs
    ) + "</div>"


def _html_glossary(paper: Paper, terms: list[GlossaryTerm]) -> str:
    if not terms:
        return ""
    items = []
    for term in terms:
        source = _html_source(
            paper.source_url,
            term.source_section,
            term.source_anchor,
            "term-source",
        )
        items.append(
            '<div class="term">'
            f"<dt>{escape(term.short_form)}</dt>"
            f"<dd>{escape(term.term)}{source}</dd>"
            "</div>"
        )
    return (
        '<section class="card wide" aria-labelledby="terms">'
        '<h2 id="terms">Terms used in the paper</h2>'
        '<p class="muted">These meanings are taken from definitions in the paper.</p>'
        f'<dl class="glossary">{"".join(items)}</dl>'
        "</section>"
    )


def _architecture_node(node: Any) -> str:
    detail = f'<small>{escape(node.detail)}</small>' if node.detail else ""
    return (
        f'<li class="architecture-node architecture-{escape(node.kind, quote=True)}" '
        f'data-node-id="{escape(node.id, quote=True)}">'
        f'<strong>{escape(node.label)}</strong>{detail}</li>'
    )


def _encoder_decoder_sources(paper: Paper, spec: VisualSpec) -> str:
    source_nodes = [
        ("Model architecture", spec.nodes[0]),
        ("Encoder stack", spec.nodes[1]),
        ("Decoder stack", spec.nodes[4]),
        ("Encoder–decoder attention", spec.nodes[5]),
    ]
    links = []
    for label, node in source_nodes:
        href = _source_href(paper.source_url, node.source_anchor)
        links.append(f'<a href="{_safe_href(href)}">{escape(label)}</a>')
    return f'<p class="source-label visual-source">Sources: {"; ".join(links)}</p>'


def _html_encoder_decoder_visual(paper: Paper, spec: VisualSpec) -> str:
    nodes = {node.id: node for node in spec.nodes}
    encoder_ids = ["input", "encoder-attention", "encoder-feed-forward"]
    decoder_ids = [
        "previous-output",
        "decoder-attention",
        "cross-attention",
        "decoder-feed-forward",
        "output",
    ]
    encoder_nodes = "".join(_architecture_node(nodes[node_id]) for node_id in encoder_ids)
    decoder_nodes = "".join(_architecture_node(nodes[node_id]) for node_id in decoder_ids)
    return (
        '<div class="architecture-diagram">'
        '<section class="architecture-lane" aria-labelledby="encoder-lane">'
        '<div class="lane-heading"><h3 id="encoder-lane">Encoder</h3>'
        '<span>Repeated layer stack</span></div>'
        f'<ol class="architecture-flow encoder-flow">{encoder_nodes}</ol>'
        "</section>"
        '<div class="architecture-bridge" aria-label="Encoder output supplies keys and values to decoder attention">'
        '<span>Encoder output</span><strong>↓</strong><span>Keys + values</span></div>'
        '<section class="architecture-lane" aria-labelledby="decoder-lane">'
        '<div class="lane-heading"><h3 id="decoder-lane">Decoder</h3>'
        '<span>Repeated layer stack</span></div>'
        f'<ol class="architecture-flow decoder-flow">{decoder_nodes}</ol>'
        "</section>"
        f"{_encoder_decoder_sources(paper, spec)}"
        "</div>"
    )


def _html_visual(paper: Paper, spec: VisualSpec) -> str:
    if spec.visual_type == "encoder-decoder":
        return _html_encoder_decoder_visual(paper, spec)
    nodes = []
    for index, node in enumerate(spec.nodes, start=1):
        nodes.append(
            f'<li class="visual-node" data-step="{index - 1}">'
            f'<span class="visual-number">{index:02d}</span>'
            f'<strong>{escape(node.label)}</strong>'
            "</li>"
        )
    source = ""
    if spec.visual_type != "paper-outline":
        first_node = spec.nodes[0]
        source = _html_source(
            paper.source_url,
            first_node.source_section,
            first_node.source_anchor,
            "source-label visual-source",
        )
    return (
        '<div class="visual-stage">'
        f'<ol class="visual-flow" data-visual-type="{escape(spec.visual_type, quote=True)}">{"".join(nodes)}</ol>'
        f"{source}"
        "</div>"
    )


def _list_needs_full_width(items: list[SourcedStatement]) -> bool:
    return len(items) >= 3 or sum(len(reading_text(item.text)) for item in items) > 420


def _html_list_section(
    paper: Paper,
    key: str,
    heading: str,
    items: list[SourcedStatement],
    *,
    wide: bool,
) -> str:
    card_class = "card wide" if wide else "card"
    return (
        f'<section class="{card_class}" aria-labelledby="{escape(key, quote=True)}">'
        f'<h2 id="{escape(key, quote=True)}">{escape(heading)}</h2>'
        f"{_html_list(paper, items)}</section>"
    )


def render_html(
    paper: Paper,
    digest: Digest,
    comparison: ComparisonSet | None = None,
    output_quality: OutputQuality | None = None,
) -> str:
    """Render a portable, dependency-free learning card safe to open locally."""

    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    if output_quality is None:
        digest, output_quality = apply_output_quality_rules(
            paper, digest, visual, glossary
        )
    agent_json = escape(render_json(paper, digest, comparison, output_quality))

    problem_shown = section_is_shown(output_quality, "problem")
    core_idea_shown = section_is_shown(output_quality, "core_idea")
    intro_wide = problem_shown != core_idea_shown
    problem_card = ""
    if problem_shown:
        problem_class = "card wide" if intro_wide else "card"
        problem_card = (
            f'<section class="{problem_class}" aria-labelledby="problem">'
            f'<h2 id="problem">The problem</h2>{_html_statement(paper, digest.problem)}'
            "</section>"
        )
    core_idea_card = ""
    if core_idea_shown:
        core_idea_class = "card wide" if intro_wide else "card"
        core_idea_card = (
            f'<section class="{core_idea_class}" aria-labelledby="idea">'
            f'<h2 id="idea">The core idea</h2>{_html_statement(paper, digest.core_idea)}'
            "</section>"
        )

    visual_card = ""
    if section_is_shown(output_quality, "visual"):
        visual_card = (
            '<section class="card wide" aria-labelledby="visual">'
            f'<h2 id="visual">{escape(visual.title)}</h2>{_html_visual(paper, visual)}'
            "</section>"
        )
    paper_map = "" if visual.visual_type == "paper-outline" or not visual_card else (
        '<section class="card wide" aria-labelledby="map">'
        '<h2 id="map">Paper map</h2>'
        f'{_html_paper_map(paper)}</section>'
    )

    body_specs = []
    if section_is_shown(output_quality, "evidence"):
        body_specs.append(
            ("evidence", _results_heading(digest), digest.evidence)
        )
    if section_is_shown(output_quality, "limitations"):
        body_specs.append(("limits", "Limitations", digest.limitations))
    if section_is_shown(output_quality, "takeaways"):
        body_specs.append(
            ("remember", "Key points from the discussion", digest.takeaways)
        )
    wide_sections = {
        key for key, _, items in body_specs if _list_needs_full_width(items)
    }
    compact_keys = [key for key, _, _ in body_specs if key not in wide_sections]
    if len(compact_keys) % 2:
        wide_sections.add(compact_keys[-1])
    body_cards = "".join(
        _html_list_section(
            paper,
            key,
            heading,
            items,
            wide=key in wide_sections,
        )
        for key, heading, items in body_specs
    )
    glossary_card = (
        _html_glossary(paper, glossary)
        if section_is_shown(output_quality, "glossary")
        else ""
    )
    abstract_card = ""
    if section_is_shown(output_quality, "abstract"):
        abstract_card = (
            '<section class="card wide" aria-labelledby="abstract">'
            f'<h2 id="abstract">Abstract</h2>{_html_abstract(paper.abstract)}'
            f'<p class="source-label">Keywords: {escape(keywords)}</p></section>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>{escape(paper.title)} · RPL</title>
  <style>
    :root {{ color-scheme:light; --bg:#fff; --surface:#fff; --surface-solid:#fff; --ink:#1d1d1f; --muted:#6e6e73; --line:rgba(60,60,67,.18); --line-strong:rgba(60,60,67,.3); --accent:#007aff; --accent-strong:#0066cc; --code:#1c1c1e; --code-ink:#f5f5f7; --shadow:0 1px 2px rgba(0,0,0,.03),0 8px 24px rgba(0,0,0,.045); }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; font-size:100%; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:clamp(1rem,.97rem + .18vw,1.0625rem)/1.58 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue","Segoe UI",sans-serif; letter-spacing:-.011em; -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }}
    a {{ color:var(--accent-strong); text-decoration-thickness:.08em; text-underline-offset:.2em; }}
    a:hover {{ color:var(--accent); }}
    a:focus-visible,summary:focus-visible {{ outline:3px solid var(--accent); outline-offset:3px; border-radius:6px; }}
    .skip-link {{ position:fixed; z-index:20; top:10px; left:10px; padding:10px 14px; border-radius:10px; background:var(--surface-solid); color:var(--ink); font-weight:650; transform:translateY(-150%); box-shadow:var(--shadow); }}
    .skip-link:focus {{ transform:none; }}
    .shell {{ width:min(1160px,calc(100% - 40px)); margin:0 auto; }}
    .hero {{ padding:clamp(48px,7vw,88px) 0 clamp(34px,5vw,56px); border-bottom:1px solid var(--line); }}
    .hero-copy {{ max-width:960px; }}
    .source-label {{ color:var(--muted); font-size:.82rem; font-weight:400; font-style:italic; letter-spacing:0; }}
    h1,h2,h3,.visual-node strong,.architecture-node strong {{ font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue","Segoe UI",sans-serif; }}
    h1 {{ max-width:940px; margin:0 0 1.35rem; font-size:clamp(2.55rem,6vw,4.75rem); line-height:1.03; font-weight:750; letter-spacing:-.05em; text-wrap:balance; }}
    h2 {{ margin:0 0 1.1rem; font-size:clamp(1.45rem,2.4vw,1.9rem); line-height:1.16; font-weight:700; letter-spacing:-.027em; text-wrap:balance; }}
    p {{ margin:.45rem 0 1rem; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:.5rem 1.15rem; color:var(--muted); font-size:.94rem; }}
    .meta span {{ max-width:100%; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); grid-auto-flow:row dense; align-items:start; gap:16px; padding:28px 0 44px; }}
    .card {{ min-width:0; background:var(--surface); border:1px solid var(--line); border-radius:20px; padding:clamp(22px,3vw,32px); box-shadow:var(--shadow); }}
    .wide {{ grid-column:1/-1; }}
    .wide > p {{ max-width:78ch; }}
    .muted {{ color:var(--muted); }}
    .source-label {{ margin:1rem 0 0; }}
    .statement-list {{ display:grid; gap:0; margin:0; padding:0; list-style:none; }}
    .statement {{ padding:14px 0; border-top:1px solid var(--line); }}
    .statement:first-child {{ padding-top:0; border-top:0; }}
    .statement:last-child {{ padding-bottom:0; }}
    .statement p:first-child {{ margin-top:0; }}
    .statement p:last-child {{ margin-bottom:0; }}
    .paper-map {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); column-gap:28px; margin:0; padding:0; list-style:none; }}
    .map-node {{ display:grid; grid-template-columns:2rem 1fr; gap:10px; padding:10px 0; border-top:1px solid var(--line); font-weight:600; }}
    .map-node:nth-child(1),.map-node:nth-child(2) {{ border-top:0; }}
    .map-number {{ color:var(--muted); font-size:.78rem; font-weight:500; }}
    .visual-flow {{ display:flex; align-items:stretch; gap:28px; margin:0; padding:0 2px 6px; list-style:none; overflow-x:auto; scrollbar-width:thin; }}
    .visual-node {{ position:relative; flex:1 0 160px; min-height:148px; display:flex; flex-direction:column; justify-content:space-between; gap:14px; padding:18px; border:1px solid var(--line-strong); border-radius:18px; background:var(--surface-solid); }}
    .visual-node:not(:last-child)::after {{ content:"→"; position:absolute; left:calc(100% + 8px); top:50%; width:12px; color:var(--muted); font-weight:700; transform:translateY(-50%); }}
    .visual-number {{ color:var(--muted); font-size:.72rem; font-weight:600; letter-spacing:.035em; }}
    .visual-node strong {{ font-size:1.15rem; line-height:1.2; font-weight:700; letter-spacing:-.015em; }}
    .visual-flow[data-visual-type="paper-outline"] {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 28px; overflow:visible; padding:0; }}
    .visual-flow[data-visual-type="paper-outline"] .visual-node {{ min-height:0; display:grid; grid-template-columns:2rem 1fr; align-items:center; gap:10px; padding:11px 0; border:0; border-top:1px solid var(--line); border-radius:0; }}
    .visual-flow[data-visual-type="paper-outline"] .visual-node:nth-child(1),.visual-flow[data-visual-type="paper-outline"] .visual-node:nth-child(2) {{ border-top:0; }}
    .visual-flow[data-visual-type="paper-outline"] .visual-node::after {{ content:none; }}
    .visual-flow[data-visual-type="paper-outline"] .visual-node strong {{ font-size:1rem; font-weight:600; }}
    .architecture-diagram {{ display:grid; gap:18px; }}
    .architecture-lane {{ padding:18px; border:1px solid var(--line); border-radius:16px; background:var(--surface-solid); }}
    .lane-heading {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:14px; }}
    .lane-heading h3 {{ margin:0; font-size:1.08rem; line-height:1.2; letter-spacing:-.015em; }}
    .lane-heading span {{ color:var(--muted); font-size:.8rem; }}
    .architecture-flow {{ display:grid; gap:22px; margin:0; padding:0; list-style:none; }}
    .encoder-flow {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
    .decoder-flow {{ grid-template-columns:repeat(5,minmax(0,1fr)); }}
    .architecture-node {{ position:relative; min-height:94px; display:flex; flex-direction:column; justify-content:center; gap:5px; padding:14px; border:1px solid var(--line-strong); border-radius:13px; background:var(--surface); }}
    .architecture-node:not(:last-child)::after {{ content:"→"; position:absolute; left:calc(100% + 6px); top:50%; width:10px; color:var(--muted); font-weight:700; transform:translateY(-50%); }}
    .architecture-node strong {{ font-size:.98rem; line-height:1.25; font-weight:650; }}
    .architecture-node small {{ color:var(--muted); font-size:.75rem; line-height:1.3; }}
    .architecture-input,.architecture-output {{ background:rgba(0,122,255,.055); border-color:rgba(0,122,255,.25); }}
    .architecture-bridge {{ justify-self:center; display:grid; grid-template-columns:auto auto auto; align-items:center; gap:10px; color:var(--muted); font-size:.8rem; }}
    .architecture-bridge strong {{ color:var(--accent-strong); font-size:1.15rem; }}
    .source-label a,.term-source a {{ color:inherit; }}
    .glossary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:18px 0 0; }}
    .term {{ padding:16px; border:1px solid var(--line); border-radius:16px; background:var(--surface-solid); }}
    .term dt {{ color:var(--ink); font-weight:750; }}
    .term dd {{ margin:4px 0 0; }}
    .term-source {{ margin:10px 0 0; color:var(--muted); font-size:.72rem; font-weight:650; letter-spacing:.025em; text-transform:uppercase; }}
    .abstract-text {{ max-width:72ch; }}
    .abstract-text p {{ margin:0 0 .85rem; }}
    details {{ border-top:1px solid var(--line); padding-top:16px; }}
    summary {{ display:flex; align-items:center; min-height:44px; cursor:pointer; font-weight:650; }}
    pre {{ max-height:420px; overflow:auto; padding:18px; border-radius:14px; background:var(--code); color:var(--code-ink); font:13px/1.55 ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
    @media (max-width:720px) {{ .shell {{ width:min(100% - 24px,1160px); }} .hero {{ padding-top:48px; }} h1 {{ font-size:clamp(2.35rem,12vw,3.5rem); }} .grid {{ grid-template-columns:1fr; gap:12px; padding-top:18px; }} .wide {{ grid-column:auto; }} .card {{ border-radius:18px; padding:22px 20px; }} .visual-flow {{ display:grid; overflow:visible; }} .visual-node {{ min-height:96px; }} .visual-node:not(:last-child)::after {{ content:"↓"; left:50%; top:calc(100% + 5px); transform:translateX(-50%); }} .map-node:nth-child(2) {{ border-top:1px solid var(--line); }} .visual-flow[data-visual-type="paper-outline"] {{ grid-template-columns:1fr; }} .visual-flow[data-visual-type="paper-outline"] .visual-node:nth-child(2) {{ border-top:1px solid var(--line); }} .lane-heading {{ align-items:flex-start; flex-direction:column; gap:3px; }} .encoder-flow,.decoder-flow {{ grid-template-columns:1fr; }} .architecture-node {{ min-height:78px; }} .architecture-node:not(:last-child)::after {{ content:"↓"; left:50%; top:calc(100% + 4px); transform:translateX(-50%); }} .architecture-bridge {{ grid-template-columns:1fr; justify-items:center; gap:2px; }} }}
    @media (prefers-contrast:more) {{ :root {{ --line:rgba(60,60,67,.42); --line-strong:rgba(60,60,67,.72); }} .card,.term,.visual-node {{ border-width:2px; }} .muted,.meta,.source-label,.visual-number {{ color:var(--ink); }} }}
    @media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} *,*::before,*::after {{ scroll-behavior:auto!important; transition-duration:.01ms!important; animation-duration:.01ms!important; animation-iteration-count:1!important; }} }}
    @media print {{ :root {{ --ink:#000; --muted:#444; --line:#bbb; --shadow:none; }} .shell {{ width:100%; }} .hero {{ padding:20px 0; }} .card {{ break-inside:avoid; box-shadow:none; }} details {{ display:none; }} }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <header class="hero">
    <div class="shell hero-copy">
      <h1>{escape(paper.title)}</h1>
      <div class="meta">
        <span>{escape(authors)}</span>
        <span>{escape(paper.published or "Publication date unknown")}</span>
        <span><a href="{_safe_href(paper.source_url)}">Open original · {escape(paper.paper_id)}</a></span>
      </div>
    </div>
  </header>
  <main class="shell grid" id="main-content">
    {problem_card}
    {core_idea_card}
    {visual_card}
    {paper_map}
    {body_cards}
    {glossary_card}
    {abstract_card}
    <section class="card wide" aria-labelledby="agent-data">
      <h2 id="agent-data">Structured data</h2>
      <p>Use this JSON with an AI agent, script, or research library.</p>
      <details><summary>Show JSON</summary><pre>{agent_json}</pre></details>
    </section>
  </main>
</body>
</html>
"""
