from __future__ import annotations

import json
import re
from typing import Any

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

