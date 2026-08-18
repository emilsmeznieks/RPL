from __future__ import annotations

import base64
import hashlib
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
    Paper,
    SourcedStatement,
    VisualSpec,
)
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


def knowledge_payload(
    paper: Paper, digest: Digest, comparison: ComparisonSet | None = None
) -> dict[str, Any]:
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    comparison = comparison or empty_comparison_set(paper)
    if comparison.focal_paper_id != paper.paper_id:
        raise ValueError("The comparison focal paper must match the rendered paper.")
    validate_comparison_set(comparison)
    return {
        "schema_version": "0.6",
        "paper": paper.to_dict(),
        "digest": digest.to_dict(),
        "visual": visual.to_dict(),
        "glossary": [term.to_dict() for term in glossary],
        "comparison": comparison.to_dict(),
        "provenance": {
            "source_url": paper.source_url,
            "extraction_method": digest.extraction_method,
            "generated_claims": False,
        },
    }


def render_json(
    paper: Paper, digest: Digest, comparison: ComparisonSet | None = None
) -> str:
    return json.dumps(
        knowledge_payload(paper, digest, comparison), indent=2, ensure_ascii=False
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


def render_html(
    paper: Paper, digest: Digest, comparison: ComparisonSet | None = None
) -> str:
    """Render a portable, dependency-free learning card safe to open locally."""

    authors = ", ".join(paper.authors) or "Unknown authors"
    keywords = ", ".join(paper.keywords) or "Not provided"
    visual = build_visual_spec(paper)
    glossary = build_glossary(paper)
    agent_json = escape(render_json(paper, digest, comparison))
    script_hash = _interaction_script_hash()
    paper_type = {
        "empirical": "Empirical paper",
        "theoretical": "Theoretical paper",
    }.get(digest.paper_type, "Paper type uncertain")
    type_confidence = f"{digest.paper_type_confidence.capitalize()} confidence"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>{escape(paper.title)} · RPL</title>
  <style>
    :root {{ color-scheme:light dark; --bg:#f5f5f7; --surface:rgba(255,255,255,.86); --surface-solid:#fff; --surface-raised:#fff; --ink:#1d1d1f; --muted:#6e6e73; --line:rgba(60,60,67,.18); --line-strong:rgba(60,60,67,.3); --accent:#007aff; --accent-strong:#0066cc; --accent-soft:rgba(0,122,255,.09); --code:#1c1c1e; --code-ink:#f5f5f7; --shadow:0 1px 2px rgba(0,0,0,.04),0 12px 32px rgba(0,0,0,.06); }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; font-size:100%; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:clamp(1rem,.97rem + .18vw,1.0625rem)/1.58 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue","Segoe UI",sans-serif; letter-spacing:-.011em; -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }}
    a {{ color:var(--accent-strong); text-decoration-thickness:.08em; text-underline-offset:.2em; }}
    a:hover {{ color:var(--accent); }}
    a:focus-visible,button:focus-visible,summary:focus-visible {{ outline:3px solid var(--accent); outline-offset:3px; border-radius:6px; }}
    .skip-link {{ position:fixed; z-index:20; top:10px; left:10px; padding:10px 14px; border-radius:10px; background:var(--surface-solid); color:var(--ink); font-weight:650; transform:translateY(-150%); box-shadow:var(--shadow); }}
    .skip-link:focus {{ transform:none; }}
    .shell {{ width:min(1160px,calc(100% - 40px)); margin:0 auto; }}
    .hero {{ padding:clamp(56px,8vw,104px) 0 clamp(38px,5vw,64px); background:linear-gradient(180deg,var(--surface-solid),var(--bg)); border-bottom:1px solid var(--line); }}
    .hero-copy {{ max-width:960px; }}
    .eyebrow,.source-label {{ color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.045em; text-transform:uppercase; }}
    h1,h2,.visual-node strong {{ font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue","Segoe UI",sans-serif; }}
    h1 {{ max-width:940px; margin:.45rem 0 1.35rem; font-size:clamp(2.55rem,6vw,4.75rem); line-height:1.03; font-weight:750; letter-spacing:-.05em; text-wrap:balance; }}
    h2 {{ margin:0 0 1.1rem; font-size:clamp(1.45rem,2.4vw,1.9rem); line-height:1.16; font-weight:700; letter-spacing:-.027em; text-wrap:balance; }}
    p {{ margin:.45rem 0 1rem; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:.5rem 1.15rem; color:var(--muted); font-size:.94rem; }}
    .meta span {{ max-width:100%; }}
    .classification {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:22px; }}
    .badge {{ display:inline-flex; align-items:center; min-height:30px; padding:5px 10px; border:1px solid var(--line); border-radius:999px; background:var(--surface); color:var(--muted); font-size:.78rem; font-weight:650; letter-spacing:-.005em; backdrop-filter:blur(18px) saturate(140%); -webkit-backdrop-filter:blur(18px) saturate(140%); }}
    .badge-primary {{ border-color:rgba(0,122,255,.22); background:var(--accent-soft); color:var(--accent-strong); }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:20px; padding:32px 0 44px; }}
    .card {{ min-width:0; background:var(--surface); border:1px solid var(--line); border-radius:24px; padding:clamp(22px,3vw,34px); box-shadow:var(--shadow); backdrop-filter:blur(24px) saturate(130%); -webkit-backdrop-filter:blur(24px) saturate(130%); }}
    .wide {{ grid-column:1/-1; }}
    .wide > p {{ max-width:78ch; }}
    .muted {{ color:var(--muted); }}
    .source-label {{ margin:1rem 0 0; }}
    .statement-list {{ display:grid; gap:10px; margin:0; padding:0; list-style:none; }}
    .statement {{ padding:16px 18px; border:1px solid var(--line); border-radius:16px; background:var(--surface-solid); }}
    .statement p:first-child {{ margin-top:0; }}
    .statement p:last-child {{ margin-bottom:0; }}
    .paper-map {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0; padding:0; list-style:none; counter-reset:item; }}
    .map-node {{ min-height:112px; display:flex; flex-direction:column; justify-content:space-between; padding:16px; border:1px solid var(--line); border-radius:16px; background:var(--surface-solid); font-weight:650; }}
    .map-number {{ color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.035em; }}
    .visual-heading {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:18px; color:var(--muted); }}
    .visual-heading p {{ margin:0; }}
    .confidence {{ flex:none; padding:5px 9px; border:1px solid var(--line); border-radius:999px; font-size:.72rem; font-weight:700; letter-spacing:.025em; text-transform:uppercase; }}
    .visual-flow {{ display:flex; align-items:stretch; gap:28px; margin:0; padding:0 2px 6px; list-style:none; overflow-x:auto; scrollbar-width:thin; }}
    .visual-node {{ position:relative; flex:1 0 160px; min-height:148px; display:flex; flex-direction:column; justify-content:space-between; gap:14px; padding:18px; border:1px solid var(--line-strong); border-radius:18px; background:var(--surface-solid); }}
    .visual-node:not(:last-child)::after {{ content:"→"; position:absolute; left:calc(100% + 8px); top:50%; width:12px; color:var(--muted); font-weight:700; transform:translateY(-50%); }}
    .visual-number,.visual-source {{ color:var(--muted); font-size:.72rem; font-weight:700; letter-spacing:.035em; text-transform:uppercase; }}
    .visual-source {{ margin:0; }}
    .visual-node strong {{ font-size:1.15rem; line-height:1.2; font-weight:700; letter-spacing:-.015em; }}
    .source-label a,.visual-source a,.term-source a {{ color:inherit; }}
    .glossary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:18px 0 0; }}
    .term {{ padding:16px; border:1px solid var(--line); border-radius:16px; background:var(--surface-solid); }}
    .term dt {{ color:var(--ink); font-weight:750; }}
    .term dd {{ margin:4px 0 0; }}
    .term-source {{ margin:10px 0 0; color:var(--muted); font-size:.72rem; font-weight:650; letter-spacing:.025em; text-transform:uppercase; }}
    .visual-controls {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-top:18px; }}
    .visual-controls[hidden] {{ display:none; }}
    .visual-buttons {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .visual-buttons button {{ min-height:44px; padding:10px 15px; border:1px solid var(--line-strong); border-radius:12px; background:var(--surface-solid); color:var(--ink); cursor:pointer; font:inherit; font-size:.94rem; font-weight:650; }}
    .visual-buttons button:hover:not(:disabled) {{ border-color:var(--accent); background:var(--accent-soft); color:var(--accent-strong); }}
    .visual-buttons button:active:not(:disabled) {{ transform:scale(.98); }}
    .visual-buttons button:disabled {{ cursor:not-allowed; opacity:.38; }}
    .visual-status {{ margin:0; color:var(--muted); font-size:.88rem; font-weight:650; text-align:right; }}
    .is-interactive .visual-node {{ opacity:.5; transition:opacity .22s ease,transform .22s ease,box-shadow .22s ease,border-color .22s ease; }}
    .is-interactive .visual-node.is-complete {{ opacity:.72; }}
    .is-interactive .visual-node.is-current {{ z-index:1; opacity:1; transform:translateY(-3px); border-color:rgba(0,122,255,.55); box-shadow:0 8px 24px rgba(0,122,255,.12); }}
    details {{ border-top:1px solid var(--line); padding-top:16px; }}
    summary {{ display:flex; align-items:center; min-height:44px; cursor:pointer; font-weight:650; }}
    pre {{ max-height:420px; overflow:auto; padding:18px; border-radius:14px; background:var(--code); color:var(--code-ink); font:13px/1.55 ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
    footer {{ padding:8px 0 52px; color:var(--muted); font-size:.88rem; }}
    @media (max-width:720px) {{ .shell {{ width:min(100% - 24px,1160px); }} .hero {{ padding-top:48px; }} h1 {{ font-size:clamp(2.35rem,12vw,3.5rem); }} .grid {{ grid-template-columns:1fr; gap:12px; padding-top:18px; }} .wide {{ grid-column:auto; }} .card {{ border-radius:20px; padding:22px 20px; }} .visual-heading,.visual-controls {{ align-items:flex-start; flex-direction:column; }} .visual-flow {{ display:grid; overflow:visible; }} .visual-node {{ min-height:112px; }} .visual-node:not(:last-child)::after {{ content:"↓"; left:50%; top:calc(100% + 5px); transform:translateX(-50%); }} .visual-status {{ text-align:left; }} }}
    @media (prefers-color-scheme:dark) {{ :root {{ --bg:#000; --surface:rgba(28,28,30,.88); --surface-solid:#1c1c1e; --surface-raised:#2c2c2e; --ink:#f5f5f7; --muted:#aeaeb2; --line:rgba(84,84,88,.56); --line-strong:rgba(99,99,102,.72); --accent:#0a84ff; --accent-strong:#64d2ff; --accent-soft:rgba(10,132,255,.16); --code:#111; --code-ink:#f5f5f7; --shadow:0 1px 2px rgba(0,0,0,.25),0 14px 36px rgba(0,0,0,.3); }} .hero {{ background:linear-gradient(180deg,#111,var(--bg)); }} }}
    @media (prefers-contrast:more) {{ :root {{ --line:rgba(60,60,67,.42); --line-strong:rgba(60,60,67,.72); }} .card,.statement,.map-node,.term,.visual-node {{ border-width:2px; }} .muted,.meta,.source-label,.visual-number,.visual-source {{ color:var(--ink); }} }}
    @media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} *,*::before,*::after {{ scroll-behavior:auto!important; transition-duration:.01ms!important; animation-duration:.01ms!important; animation-iteration-count:1!important; }} }}
    @media print {{ :root {{ color-scheme:light; --bg:#fff; --surface:#fff; --surface-solid:#fff; --ink:#000; --muted:#444; --line:#bbb; --shadow:none; }} body {{ background:white; }} .shell {{ width:100%; }} .hero {{ padding:20px 0; background:white; }} .card {{ break-inside:avoid; box-shadow:none; backdrop-filter:none; }} details,.visual-controls {{ display:none; }} .is-interactive .visual-node {{ opacity:1; transform:none; box-shadow:none; }} }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <header class="hero">
    <div class="shell hero-copy">
      <div class="eyebrow">RPL · Research paper guide</div>
      <h1>{escape(paper.title)}</h1>
      <div class="meta">
        <span>{escape(authors)}</span>
        <span>{escape(paper.published or "Publication date unknown")}</span>
        <span><a href="{_safe_href(paper.source_url)}">Open original · {escape(paper.paper_id)}</a></span>
      </div>
      <div class="classification" aria-label="RPL paper classification">
        <span class="badge badge-primary">{escape(paper_type)}</span>
        <span class="badge">{escape(type_confidence)}</span>
      </div>
    </div>
  </header>
  <main class="shell grid" id="main-content">
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
