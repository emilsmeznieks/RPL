from __future__ import annotations

import json
import re
from html import escape
from typing import Any
from urllib.parse import urlparse

from .models import Digest, Paper, SourcedStatement


def _markdown_statement(item: SourcedStatement | None) -> str:
    if item is None:
        return "Not confidently identified by the deterministic extractor."
    return f"{item.text}\n\n_Source: {item.section}_"


def _markdown_list(items: list[SourcedStatement]) -> str:
    if not items:
        return "- Not confidently identified by the deterministic extractor."
    return "\n".join(f"- {item.text} _(Source: {item.section})_" for item in items)


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


def render_markdown(paper: Paper, digest: Digest) -> str:
    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    return f"""# {paper.title}

> RPL extractive learning card · [{paper.paper_id}]({paper.source_url})

**Authors:** {authors}  
**Published:** {paper.published or "Unknown"}  
**Keywords:** {keywords}

## The problem

{_markdown_statement(digest.problem)}

## The core idea

{_markdown_statement(digest.core_idea)}

## Evidence worth checking

{_markdown_list(digest.evidence)}

## Limitations

{_markdown_list(digest.limitations)}

## What to remember

{_markdown_list(digest.takeaways)}

## Paper map

```mermaid
{outline_mermaid(paper)}
```

## Abstract

{paper.abstract or "No abstract extracted."}

---

This card was produced by `{digest.extraction_method}`. It selects text from the paper and does not yet use an LLM. Always verify important claims in the original source.
"""


def knowledge_payload(paper: Paper, digest: Digest) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "paper": paper.to_dict(),
        "digest": digest.to_dict(),
        "provenance": {
            "source_url": paper.source_url,
            "extraction_method": digest.extraction_method,
            "generated_claims": False,
        },
    }


def render_json(paper: Paper, digest: Digest) -> str:
    return json.dumps(knowledge_payload(paper, digest), indent=2, ensure_ascii=False) + "\n"


def _safe_href(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"https", "http", "file"}:
        return escape(value, quote=True)
    return "#"


def _html_statement(item: SourcedStatement | None) -> str:
    if item is None:
        return '<p class="muted">Not confidently identified by the deterministic extractor.</p>'
    return (
        f"<p>{escape(item.text)}</p>"
        f'<p class="source-label">Source · {escape(item.section)}</p>'
    )


def _html_list(items: list[SourcedStatement]) -> str:
    if not items:
        return '<p class="muted">Not confidently identified by the deterministic extractor.</p>'
    cards = []
    for item in items:
        cards.append(
            '<li class="statement">'
            f"<p>{escape(item.text)}</p>"
            f'<p class="source-label">Source · {escape(item.section)}</p>'
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


def render_html(paper: Paper, digest: Digest) -> str:
    """Render a portable, dependency-free learning card safe to open locally."""

    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    agent_json = escape(render_json(paper, digest))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>{escape(paper.title)} · RPL</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f4f1e9; --surface:#fffdf7; --ink:#17221d; --muted:#65716a; --line:#d7d6cd; --accent:#245f4b; --soft:#e3eee8; --warning:#8b4a2f; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.65 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    a {{ color:var(--accent); text-underline-offset:.18em; }}
    .shell {{ width:min(1120px,calc(100% - 32px)); margin:0 auto; }}
    .hero {{ padding:72px 0 42px; border-bottom:1px solid var(--line); }}
    .eyebrow,.source-label {{ color:var(--accent); font-size:.76rem; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }}
    h1 {{ max-width:900px; margin:.35rem 0 1.2rem; font:clamp(2.2rem,6vw,5rem)/1.02 ui-serif,Georgia,serif; letter-spacing:-.045em; }}
    h2 {{ margin:0 0 1rem; font:clamp(1.45rem,3vw,2.1rem)/1.15 ui-serif,Georgia,serif; }}
    p {{ margin:.4rem 0 1rem; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:.45rem 1.2rem; color:var(--muted); }}
    .meta span {{ max-width:100%; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:18px; padding:32px 0; }}
    .card {{ background:var(--surface); border:1px solid var(--line); border-radius:18px; padding:clamp(20px,3vw,32px); box-shadow:0 8px 30px rgb(25 40 31 / .05); }}
    .wide {{ grid-column:1/-1; }}
    .muted {{ color:var(--muted); font-style:italic; }}
    .source-label {{ margin:1rem 0 0; }}
    .statement-list {{ display:grid; gap:12px; margin:0; padding:0; list-style:none; }}
    .statement {{ padding:14px 16px; border-left:3px solid var(--accent); background:var(--soft); border-radius:0 10px 10px 0; }}
    .statement p:first-child {{ margin-top:0; }}
    .statement p:last-child {{ margin-bottom:0; }}
    .paper-map {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin:0; padding:0; list-style:none; counter-reset:item; }}
    .map-node {{ min-height:118px; display:flex; flex-direction:column; justify-content:space-between; padding:16px; border:1px solid var(--line); border-radius:12px; background:var(--bg); font-weight:700; }}
    .map-number {{ color:var(--accent); font-size:.78rem; letter-spacing:.1em; }}
    details {{ border-top:1px solid var(--line); padding-top:16px; }}
    summary {{ cursor:pointer; font-weight:700; }}
    pre {{ max-height:420px; overflow:auto; padding:16px; border-radius:10px; background:#101915; color:#e7f3ec; font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
    footer {{ padding:12px 0 48px; color:var(--muted); font-size:.9rem; }}
    @media (max-width:720px) {{ .hero {{ padding-top:46px; }} .grid {{ grid-template-columns:1fr; }} .wide {{ grid-column:auto; }} }}
    @media (prefers-color-scheme:dark) {{ :root {{ --bg:#111713; --surface:#18201b; --ink:#eef4ef; --muted:#aab6ae; --line:#344038; --accent:#8ed0b0; --soft:#21352b; --warning:#edac8b; }} .card {{ box-shadow:none; }} }}
    @media print {{ :root {{ color-scheme:light; }} body {{ background:white; }} .shell {{ width:100%; }} .hero {{ padding:20px 0; }} .card {{ break-inside:avoid; box-shadow:none; }} details {{ display:none; }} }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="shell">
      <div class="eyebrow">RPL · Extractive learning card</div>
      <h1>{escape(paper.title)}</h1>
      <div class="meta">
        <span>{escape(authors)}</span>
        <span>{escape(paper.published or "Publication date unknown")}</span>
        <span><a href="{_safe_href(paper.source_url)}">Open original · {escape(paper.paper_id)}</a></span>
      </div>
    </div>
  </header>
  <main class="shell grid">
    <section class="card" aria-labelledby="problem"><h2 id="problem">The problem</h2>{_html_statement(digest.problem)}</section>
    <section class="card" aria-labelledby="idea"><h2 id="idea">The core idea</h2>{_html_statement(digest.core_idea)}</section>
    <section class="card wide" aria-labelledby="map"><h2 id="map">Paper map</h2>{_html_paper_map(paper)}</section>
    <section class="card" aria-labelledby="evidence"><h2 id="evidence">Evidence worth checking</h2>{_html_list(digest.evidence)}</section>
    <section class="card" aria-labelledby="limits"><h2 id="limits">Limitations</h2>{_html_list(digest.limitations)}</section>
    <section class="card wide" aria-labelledby="remember"><h2 id="remember">What to remember</h2>{_html_list(digest.takeaways)}</section>
    <section class="card wide" aria-labelledby="abstract"><h2 id="abstract">Abstract</h2><p>{escape(paper.abstract)}</p><p class="source-label">Keywords · {escape(keywords)}</p></section>
    <section class="card wide" aria-labelledby="agent-data">
      <h2 id="agent-data">For AI agents</h2>
      <p>The same card as structured, provenance-aware JSON. Copy it into a local library or agent workflow.</p>
      <details><summary>Show agent-ready JSON</summary><pre>{agent_json}</pre></details>
    </section>
  </main>
  <footer class="shell">Produced by {escape(digest.extraction_method)}. RPL selects text from the paper and does not yet use an LLM. Verify important claims in the original.</footer>
</body>
</html>
"""
