from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

from .models import Paper, Section
from .source import arxiv_id


WHITESPACE = re.compile(r"\s+")
NUMBER_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+)\s*[.:]?\s*", re.I)


def clean_text(parts: list[str] | str) -> str:
    value = " ".join(parts) if isinstance(parts, list) else parts
    value = unescape(value).replace("\u200b", "")
    value = WHITESPACE.sub(" ", value).strip()
    value = re.sub(r"\s+([,.;:!?%\)])", r"\1", value)
    value = re.sub(r"([\(])\s+", r"\1", value)
    return value


class ArxivHTMLParser(HTMLParser):
    """Small arXiv HTML parser that deliberately avoids provider dependencies."""

    capture_tags = {"h1", "h2", "h3", "h4", "p", "figcaption"}
    ignored_tags = {"script", "style", "noscript"}
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, list[str]] = {}
        self.sections: list[Section] = []
        self.abstract_parts: list[str] = []
        self.document_title = ""
        self.authors: list[str] = []
        self.infobox = ""

        self._depth = 0
        self._abstract_depth: int | None = None
        self._ignored_depth: int | None = None
        self._math_depth: int | None = None
        self._capture_tag: str | None = None
        self._capture_depth: int | None = None
        self._capture_parts: list[str] = []
        self._capture_class = ""
        self._capture_in_abstract = False
        self._capture_kind = ""

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.void_tags:
            self._depth += 1
        attributes = self._attributes(attrs)

        if tag in self.ignored_tags and self._ignored_depth is None:
            self._ignored_depth = self._depth

        if tag == "meta":
            name = attributes.get("name", "").lower()
            content = clean_text(attributes.get("content", ""))
            if name and content:
                self.metadata.setdefault(name, []).append(content)

        classes = set(attributes.get("class", "").split())
        if tag == "div" and "ltx_abstract" in classes and self._abstract_depth is None:
            self._abstract_depth = self._depth

        if tag == "math":
            equation = clean_text(attributes.get("alttext", ""))
            if equation and self.sections and equation not in self.sections[-1].equations:
                self.sections[-1].equations.append(equation)
            if equation and self._capture_tag is not None:
                self._capture_parts.append(equation)
            self._math_depth = self._depth

        special_kind = ""
        if tag == "span" and "ltx_personname" in classes:
            special_kind = "author"
        elif tag == "div" and attributes.get("id") == "watermark-tr":
            special_kind = "infobox"

        if (
            (tag in self.capture_tags or special_kind)
            and self._capture_tag is None
            and self._ignored_depth is None
        ):
            self._capture_tag = tag
            self._capture_depth = self._depth
            self._capture_parts = []
            self._capture_class = attributes.get("class", "")
            self._capture_in_abstract = self._abstract_depth is not None
            self._capture_kind = special_kind

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            attributes = self._attributes(attrs)
            name = attributes.get("name", "").lower()
            content = clean_text(attributes.get("content", ""))
            if name and content:
                self.metadata.setdefault(name, []).append(content)

    def handle_data(self, data: str) -> None:
        if self._capture_tag is not None and self._ignored_depth is None and self._math_depth is None:
            cleaned = clean_text(data)
            if cleaned:
                self._capture_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_tag == tag and self._capture_depth == self._depth:
            self._finish_capture()

        if self._abstract_depth == self._depth and tag == "div":
            self._abstract_depth = None
        if self._ignored_depth == self._depth and tag in self.ignored_tags:
            self._ignored_depth = None
        if self._math_depth == self._depth and tag == "math":
            self._math_depth = None
        if tag not in self.void_tags:
            self._depth = max(0, self._depth - 1)

    def _finish_capture(self) -> None:
        tag = self._capture_tag
        text = clean_text(self._capture_parts)
        css_class = self._capture_class
        in_abstract = self._capture_in_abstract
        capture_kind = self._capture_kind

        self._capture_tag = None
        self._capture_depth = None
        self._capture_parts = []
        self._capture_class = ""
        self._capture_in_abstract = False
        self._capture_kind = ""

        if not text or tag is None:
            return

        if capture_kind == "author":
            if text not in self.authors:
                self.authors.append(text)
            return

        if capture_kind == "infobox":
            self.infobox = text
            return

        if tag == "h1" and ("ltx_title_document" in css_class or not self.document_title):
            self.document_title = re.sub(r"^Title:\s*", "", text, flags=re.I)
            return

        if tag in {"h2", "h3", "h4"}:
            title = NUMBER_PREFIX.sub("", text).strip()
            if title:
                self.sections.append(Section(title=title, level=int(tag[1])))
            return

        if tag == "p":
            if in_abstract:
                self.abstract_parts.append(text)
            elif self.sections:
                self.sections[-1].paragraphs.append(text)
            return

        if tag == "figcaption" and self.sections:
            self.sections[-1].figures.append(text)

    def paper(self, source_url: str) -> Paper:
        def first(name: str, fallback: str = "") -> str:
            values = self.metadata.get(name, [])
            return values[0] if values else fallback

        title = first("citation_title", self.document_title or "Untitled paper")
        identifier = first("citation_arxiv_id") or arxiv_id(source_url) or arxiv_id(self.infobox) or "unknown"
        infobox_date = re.search(r"\b\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\b", self.infobox)
        keywords: list[str] = []
        for value in self.metadata.get("citation_keywords", []):
            keywords.extend(item.strip() for item in re.split(r"[,;]", value) if item.strip())

        return Paper(
            paper_id=identifier,
            title=title,
            authors=self.metadata.get("citation_author", []) or self.authors,
            published=first("citation_date") or (infobox_date.group(0) if infobox_date else None),
            source_url=source_url,
            abstract=clean_text(self.abstract_parts),
            keywords=keywords,
            sections=self.sections,
        )


def parse_arxiv_html(html: str, source_url: str) -> Paper:
    parser = ArxivHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.paper(source_url)
