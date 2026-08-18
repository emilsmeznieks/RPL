from __future__ import annotations

import base64
import hashlib
import json
import re
from html import escape
from typing import Any
from urllib.parse import quote, urlparse

from .language import build_glossary, reading_text
from .models import Digest, GlossaryTerm, Paper, SourcedStatement, VisualSpec
from .visual import build_visual_spec


INTERACTION_SCRIPT = """(() => {
  const root = document.querySelector("[data-rpl-visual]");
  if (!root) return;
  const nodes = [...root.querySelectorAll(".visual-node")];
  const controls = root.querySelector(".visual-controls");
  const status = root.querySelector(".visual-status");
  const previous = root.querySelector('[data-action="previous"]');
  const play = root.querySelector('[data-action="play"]');
  const pause = root.querySelector('[data-action="pause"]');
  const next = root.querySelector('[data-action="next"]');
  if (!nodes.length || !controls || !status || !previous || !play || !pause || !next) return;

  let index = 0;
  let timer = null;
  const interval = 1400;

  function render() {
    nodes.forEach((node, nodeIndex) => {
      node.classList.toggle("is-current", nodeIndex === index);
      node.classList.toggle("is-complete", nodeIndex < index);
      if (nodeIndex === index) node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
    });
    status.textContent = `Step ${index + 1} of ${nodes.length}: ${nodes[index].querySelector("strong").textContent}`;
    previous.disabled = index === 0;
    next.disabled = index === nodes.length - 1;
    play.disabled = timer !== null || nodes.length < 2;
    pause.disabled = timer === null;
  }

  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    root.classList.remove("is-playing");
    render();
  }

  function setStep(nextIndex) {
    index = Math.max(0, Math.min(nodes.length - 1, nextIndex));
    render();
  }

  previous.addEventListener("click", () => { stop(); setStep(index - 1); });
  next.addEventListener("click", () => { stop(); setStep(index + 1); });
  pause.addEventListener("click", stop);
  play.addEventListener("click", () => {
    if (index === nodes.length - 1) index = 0;
    root.classList.add("is-playing");
    timer = window.setInterval(() => {
      if (index === nodes.length - 1) stop();
      else setStep(index + 1);
    }, interval);
    render();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });

  root.classList.add("is-interactive");
  controls.hidden = false;
  render();
})();"""


def _interaction_script_hash() -> str:
    digest = hashlib.sha256(INTERACTION_SCRIPT.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _source_href(source_url: str, anchor: str | None) -> str | None:
    if not anchor:
        return None
    base = source_url.split("#", 1)[0]
    return f"{base}#{quote(anchor, safe='')}"


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


def _markdown_list(paper: Paper, items: list[SourcedStatement]) -> str:
    if not items:
        return "- RPL could not identify this clearly from the paper."
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


def render_markdown(paper: Paper, digest: Digest) -> str:
    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    glossary = build_glossary(paper)
    return f"""# {paper.title}

> RPL paper guide · [{paper.paper_id}]({paper.source_url})

**Authors:** {authors}  
**Published:** {paper.published or "Unknown"}  
**Keywords:** {keywords}

## The problem

{_markdown_statement(paper, digest.problem)}

## The core idea

{_markdown_statement(paper, digest.core_idea)}

## {_results_heading(digest)}

{_markdown_list(paper, digest.evidence)}

## Limitations

{_markdown_list(paper, digest.limitations)}

## Key points from the discussion

{_markdown_list(paper, digest.takeaways)}

{_markdown_glossary(paper, glossary)}## Paper map

```mermaid
{outline_mermaid(paper)}
```

## Abstract

{reading_text(paper.abstract) or "No abstract extracted."}

---

RPL selected these statements from the paper. Always verify important claims in the original source.
"""


def knowledge_payload(paper: Paper, digest: Digest) -> dict[str, Any]:
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    return {
        "schema_version": "0.5",
        "paper": paper.to_dict(),
        "digest": digest.to_dict(),
        "visual": visual.to_dict(),
        "glossary": [term.to_dict() for term in glossary],
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


def _html_source(
    source_url: str, section: str, anchor: str | None, class_name: str
) -> str:
    href = _source_href(source_url, anchor)
    label = escape(section)
    if href:
        label = f'<a href="{_safe_href(href)}">{label}</a>'
    return f'<p class="{class_name}">Source · {label}</p>'


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


def _html_list(paper: Paper, items: list[SourcedStatement]) -> str:
    if not items:
        return '<p class="muted">RPL could not identify this clearly from the paper.</p>'
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


def _html_visual(paper: Paper, spec: VisualSpec) -> str:
    nodes = []
    for index, node in enumerate(spec.nodes, start=1):
        nodes.append(
            f'<li class="visual-node" data-step="{index - 1}">'
            f'<span class="visual-number">{index:02d}</span>'
            f'<strong>{escape(node.label)}</strong>'
            f"{_html_source(paper.source_url, node.source_section, node.source_anchor, 'visual-source')}"
            "</li>"
        )
    confidence = f"RPL confidence · {spec.confidence.capitalize()}"
    return (
        '<div class="visual-stage" data-rpl-visual>'
        '<div class="visual-heading">'
        f"<p>{escape(spec.description)}</p>"
        f'<span class="confidence confidence-{escape(spec.confidence)}">{escape(confidence)}</span>'
        "</div>"
        f'<ol class="visual-flow" data-visual-type="{escape(spec.visual_type, quote=True)}">{"".join(nodes)}</ol>'
        '<div class="visual-controls" hidden>'
        '<div class="visual-buttons" role="group" aria-label="Visual playback controls">'
        '<button type="button" data-action="previous">← Previous</button>'
        '<button type="button" data-action="play">Play</button>'
        '<button type="button" data-action="pause">Pause</button>'
        '<button type="button" data-action="next">Next →</button>'
        "</div>"
        '<p class="visual-status" role="status" aria-live="polite"></p>'
        "</div>"
        "</div>"
    )


def render_html(paper: Paper, digest: Digest) -> str:
    """Render a portable, dependency-free learning card safe to open locally."""

    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    agent_json = escape(render_json(paper, digest))
    script_hash = _interaction_script_hash()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; img-src data:; base-uri 'none'; form-action 'none'">
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
    .visual-heading {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:18px; color:var(--muted); }}
    .visual-heading p {{ margin:0; }}
    .confidence {{ flex:none; padding:5px 9px; border:1px solid var(--line); border-radius:999px; font-size:.72rem; font-weight:750; letter-spacing:.05em; text-transform:uppercase; }}
    .visual-flow {{ display:flex; align-items:stretch; gap:28px; margin:0; padding:0; list-style:none; overflow-x:auto; }}
    .visual-node {{ position:relative; flex:1 0 150px; min-height:150px; display:flex; flex-direction:column; justify-content:space-between; gap:14px; padding:18px; border:1px solid var(--accent); border-radius:14px; background:var(--soft); }}
    .visual-node:not(:last-child)::after {{ content:"→"; position:absolute; left:calc(100% + 8px); top:50%; width:12px; color:var(--accent); font-weight:800; transform:translateY(-50%); }}
    .visual-number,.visual-source {{ color:var(--accent); font-size:.72rem; font-weight:750; letter-spacing:.08em; text-transform:uppercase; }}
    .visual-source {{ margin:0; }}
    .visual-node strong {{ font:1.25rem/1.15 ui-serif,Georgia,serif; }}
    .source-label a,.visual-source a,.term-source a {{ color:inherit; }}
    .glossary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:18px 0 0; }}
    .term {{ padding:16px; border:1px solid var(--line); border-radius:12px; background:var(--bg); }}
    .term dt {{ color:var(--accent); font-weight:800; }}
    .term dd {{ margin:4px 0 0; }}
    .term-source {{ margin:10px 0 0; color:var(--muted); font-size:.72rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }}
    .visual-controls {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-top:18px; }}
    .visual-controls[hidden] {{ display:none; }}
    .visual-buttons {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .visual-buttons button {{ padding:8px 12px; border:1px solid var(--line); border-radius:9px; background:var(--surface); color:var(--ink); cursor:pointer; font:inherit; font-weight:700; }}
    .visual-buttons button:hover:not(:disabled) {{ border-color:var(--accent); color:var(--accent); }}
    .visual-buttons button:focus-visible {{ outline:3px solid var(--accent); outline-offset:2px; }}
    .visual-buttons button:disabled {{ cursor:not-allowed; opacity:.42; }}
    .visual-status {{ margin:0; color:var(--muted); font-size:.88rem; font-weight:650; text-align:right; }}
    .is-interactive .visual-node {{ opacity:.46; filter:saturate(.55); transition:opacity .3s ease,filter .3s ease,transform .3s ease,box-shadow .3s ease; }}
    .is-interactive .visual-node.is-complete {{ opacity:.76; filter:saturate(.8); }}
    .is-interactive .visual-node.is-current {{ z-index:1; opacity:1; filter:none; transform:translateY(-5px); box-shadow:0 10px 24px rgb(36 95 75 / .18); }}
    .is-playing .visual-node.is-current {{ animation:visual-pulse 1.4s ease-in-out infinite; }}
    @keyframes visual-pulse {{ 50% {{ box-shadow:0 10px 30px rgb(36 95 75 / .32); }} }}
    details {{ border-top:1px solid var(--line); padding-top:16px; }}
    summary {{ cursor:pointer; font-weight:700; }}
    pre {{ max-height:420px; overflow:auto; padding:16px; border-radius:10px; background:#101915; color:#e7f3ec; font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
    footer {{ padding:12px 0 48px; color:var(--muted); font-size:.9rem; }}
    @media (max-width:720px) {{ .hero {{ padding-top:46px; }} .grid {{ grid-template-columns:1fr; }} .wide {{ grid-column:auto; }} .visual-heading,.visual-controls {{ align-items:flex-start; flex-direction:column; }} .visual-flow {{ display:grid; overflow:visible; }} .visual-node {{ min-height:112px; }} .visual-node:not(:last-child)::after {{ content:"↓"; left:50%; top:calc(100% + 5px); transform:translateX(-50%); }} .visual-status {{ text-align:left; }} }}
    @media (prefers-color-scheme:dark) {{ :root {{ --bg:#111713; --surface:#18201b; --ink:#eef4ef; --muted:#aab6ae; --line:#344038; --accent:#8ed0b0; --soft:#21352b; --warning:#edac8b; }} .card {{ box-shadow:none; }} }}
    @media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} .is-interactive .visual-node {{ transition:none; }} .is-playing .visual-node.is-current {{ animation:none; }} }}
    @media print {{ :root {{ color-scheme:light; }} body {{ background:white; }} .shell {{ width:100%; }} .hero {{ padding:20px 0; }} .card {{ break-inside:avoid; box-shadow:none; }} details,.visual-controls {{ display:none; }} .is-interactive .visual-node {{ opacity:1; filter:none; transform:none; box-shadow:none; }} }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="shell">
      <div class="eyebrow">RPL · Research paper guide</div>
      <h1>{escape(paper.title)}</h1>
      <div class="meta">
        <span>{escape(authors)}</span>
        <span>{escape(paper.published or "Publication date unknown")}</span>
        <span><a href="{_safe_href(paper.source_url)}">Open original · {escape(paper.paper_id)}</a></span>
      </div>
    </div>
  </header>
  <main class="shell grid">
    <section class="card" aria-labelledby="problem"><h2 id="problem">The problem</h2>{_html_statement(paper, digest.problem)}</section>
    <section class="card" aria-labelledby="idea"><h2 id="idea">The core idea</h2>{_html_statement(paper, digest.core_idea)}</section>
    <section class="card wide" aria-labelledby="visual"><h2 id="visual">{escape(visual.title)}</h2>{_html_visual(paper, visual)}</section>
    <section class="card wide" aria-labelledby="map"><h2 id="map">Paper map</h2>{_html_paper_map(paper)}</section>
    <section class="card" aria-labelledby="evidence"><h2 id="evidence">{escape(_results_heading(digest))}</h2>{_html_list(paper, digest.evidence)}</section>
    <section class="card" aria-labelledby="limits"><h2 id="limits">Limitations</h2>{_html_list(paper, digest.limitations)}</section>
    <section class="card wide" aria-labelledby="remember"><h2 id="remember">Key points from the discussion</h2>{_html_list(paper, digest.takeaways)}</section>
    {_html_glossary(paper, glossary)}
    <section class="card wide" aria-labelledby="abstract"><h2 id="abstract">Abstract</h2><p>{escape(reading_text(paper.abstract))}</p><p class="source-label">Keywords · {escape(keywords)}</p></section>
    <section class="card wide" aria-labelledby="agent-data">
      <h2 id="agent-data">Structured data</h2>
      <p>Use this JSON with an AI agent, script, or research library.</p>
      <details><summary>Show JSON</summary><pre>{agent_json}</pre></details>
    </section>
  </main>
  <footer class="shell">RPL selected these statements from the paper. Always verify important claims in the original source.</footer>
  <script>{INTERACTION_SCRIPT}</script>
</body>
</html>
"""
