from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

from .models import FigureArtifact, Paper, Section
from .source import arxiv_id


WHITESPACE = re.compile(r"\s+")
NUMBER_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+)\s*[.:]?\s*", re.I)
AUTHOR_FOOTNOTE = re.compile(
    r"(?:\s+\d+)*(?:\s*footnotemark(?::\s*\d+)?)?\s*$", re.I
)


class PaperParseError(ValueError):
    """Raised when HTML does not contain enough paper structure to trust."""


def clean_text(parts: list[str] | str) -> str:
    value = " ".join(parts) if isinstance(parts, list) else parts
    value = unescape(value).replace("\u200b", "")
    value = WHITESPACE.sub(" ", value).strip()
    value = re.sub(r"\s+([,.;:!?%\)])", r"\1", value)
    value = re.sub(r"([\(])\s+", r"\1", value)
    return value


def clean_author(value: str) -> str:
    """Remove arXiv affiliation markers accidentally exposed as author text."""

    return AUTHOR_FOOTNOTE.sub("", clean_text(value)).strip(" ,")


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
        self._capture_id = ""
        self._capture_in_abstract = False
        self._capture_kind = ""
        self._section_anchors: list[tuple[int, str]] = []
        self._non_prose_depths: list[int] = []
        self._figure_stack: list[dict[str, object]] = []
        self._excluded_prose_count = 0

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.void_tags:
            self._depth += 1
        attributes = self._attributes(attrs)
        classes = set(attributes.get("class", "").split())

        is_equation_table = "ltx_equation" in classes or "ltx_eqn_table" in classes
        is_table = (tag == "table" and not is_equation_table) or bool(
            classes & {"ltx_table", "ltx_tabular", "ltx_tbody", "ltx_the_table"}
        )
        is_figure_panel = tag == "figure" or bool(
            classes & {"ltx_figure", "ltx_figure_panel", "ltx_subfigure"}
        )
        if (is_table or is_figure_panel) and tag not in self.void_tags:
            self._non_prose_depths.append(self._depth)

        if tag == "figure":
            self._figure_stack.append(
                {
                    "depth": self._depth,
                    "anchor": attributes.get("id", "") or None,
                    "kind": "table" if "ltx_table" in classes else "figure",
                    "saw_image": False,
                    "image_url": None,
                    "image_missing": False,
                }
            )

        if tag == "img" and self._figure_stack:
            figure = self._figure_stack[-1]
            source = attributes.get("src", "").strip()
            figure["saw_image"] = True
            figure["image_url"] = source or None
            figure["image_missing"] = (
                not source
                or "ltx_missing" in classes
                or "ltx_missing_image" in classes
            )

        if tag == "section" and attributes.get("id"):
            self._section_anchors.append((self._depth, attributes["id"]))

        if tag in self.ignored_tags and self._ignored_depth is None:
            self._ignored_depth = self._depth

        if tag == "meta":
            name = attributes.get("name", "").lower()
            content = clean_text(attributes.get("content", ""))
            if name and content:
                self.metadata.setdefault(name, []).append(content)

        if tag == "div" and "ltx_abstract" in classes and self._abstract_depth is None:
            self._abstract_depth = self._depth

        if tag == "math":
            equation = clean_text(attributes.get("alttext", ""))
            if (
                equation
                and self.sections
                and not self._non_prose_depths
                and equation not in self.sections[-1].equations
            ):
                self.sections[-1].equations.append(equation)
                self.sections[-1].equation_anchors.append(
                    attributes.get("id", "") or self.sections[-1].anchor
                )
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
            and not (tag == "p" and self._non_prose_depths)
        ):
            self._capture_tag = tag
            self._capture_depth = self._depth
            self._capture_parts = []
            self._capture_class = attributes.get("class", "")
            self._capture_id = attributes.get("id", "")
            if tag == "figcaption" and not self._capture_id and self._figure_stack:
                self._capture_id = str(self._figure_stack[-1].get("anchor") or "")
            if not self._capture_id and self._section_anchors:
                self._capture_id = self._section_anchors[-1][1]
            self._capture_in_abstract = self._abstract_depth is not None
            self._capture_kind = special_kind
        elif tag == "p" and self._capture_tag is None and self._non_prose_depths:
            self._excluded_prose_count += 1

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
        if (
            tag == "section"
            and self._section_anchors
            and self._section_anchors[-1][0] == self._depth
        ):
            self._section_anchors.pop()
        if tag == "figure" and self._figure_stack:
            if self._figure_stack[-1]["depth"] == self._depth:
                self._figure_stack.pop()
        if self._non_prose_depths and self._non_prose_depths[-1] == self._depth:
            self._non_prose_depths.pop()
        if tag not in self.void_tags:
            self._depth = max(0, self._depth - 1)

    def _finish_capture(self) -> None:
        tag = self._capture_tag
        text = clean_text(self._capture_parts)
        css_class = self._capture_class
        element_id = self._capture_id
        in_abstract = self._capture_in_abstract
        capture_kind = self._capture_kind

        self._capture_tag = None
        self._capture_depth = None
        self._capture_parts = []
        self._capture_class = ""
        self._capture_id = ""
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
                self.sections.append(
                    Section(title=title, level=int(tag[1]), anchor=element_id or None)
                )
            return

        if tag == "p":
            if in_abstract:
                self.abstract_parts.append(text)
            elif self.sections:
                self.sections[-1].paragraphs.append(text)
                self.sections[-1].paragraph_anchors.append(element_id or None)
            return

        if tag == "figcaption":
            figure = self._figure_stack[-1] if self._figure_stack else {
                "anchor": element_id or None,
                "kind": "figure",
                "saw_image": False,
                "image_url": None,
                "image_missing": False,
            }
            if figure["kind"] != "figure":
                return
            if not self.sections:
                self.sections.append(Section("Front matter", 1, anchor="S0"))
            image_status = "not-provided"
            if figure["saw_image"]:
                image_status = "unavailable" if figure["image_missing"] else "available"
            record = FigureArtifact(
                caption=text,
                anchor=element_id or figure["anchor"] or None,
                image_url=figure["image_url"] or None,
                image_status=image_status,
            )
            self.sections[-1].figures.append(text)
            self.sections[-1].figure_records.append(record)

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

        raw_authors = self.metadata.get("citation_author", []) or self.authors
        authors = []
        for value in raw_authors:
            author = clean_author(value)
            if author and author not in authors:
                authors.append(author)

        extraction_warnings: list[str] = []
        if self._excluded_prose_count:
            extraction_warnings.append(
                f"Rejected {self._excluded_prose_count} table- or figure-contained "
                "paragraph-like elements from prose extraction."
            )
        unavailable_images = sum(
            record.image_status == "unavailable"
            for section in self.sections
            for record in section.figure_records
        )
        if unavailable_images:
            extraction_warnings.append(
                f"{unavailable_images} source figure image"
                f"{'s were' if unavailable_images != 1 else ' was'} unavailable in the arXiv HTML."
            )

        return Paper(
            paper_id=identifier,
            title=title,
            authors=authors,
            published=first("citation_date") or (infobox_date.group(0) if infobox_date else None),
            source_url=source_url,
            abstract=clean_text(self.abstract_parts),
            keywords=keywords,
            sections=self.sections,
            extraction_warnings=extraction_warnings,
        )


def parse_arxiv_html(html: str, source_url: str) -> Paper:
    if not html.strip():
        raise PaperParseError("The paper source is empty.")
    parser = ArxivHTMLParser()
    parser.feed(html)
    parser.close()
    paper = parser.paper(source_url)
    missing: list[str] = []
    if paper.title == "Untitled paper":
        missing.append("title")
    if not paper.abstract:
        missing.append("abstract")
    if not paper.sections:
        missing.append("sections")
    if missing:
        fields = ", ".join(missing)
        raise PaperParseError(
            f"The source does not look like a supported arXiv HTML paper (missing: {fields})."
        )
    return paper
