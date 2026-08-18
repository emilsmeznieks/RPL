from __future__ import annotations

import re
import ssl
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi


ARXIV_ID = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?")


class SourceError(RuntimeError):
    """Raised when RPL cannot resolve or retrieve a paper source."""


def arxiv_id(value: str) -> str | None:
    match = ARXIV_ID.search(value)
    if not match:
        return None
    return match.group("id") + (match.group("version") or "")


def normalize_arxiv_url(value: str) -> str:
    """Return the canonical arXiv HTML URL for an ID or arXiv URL."""

    paper_id = arxiv_id(value)
    if not paper_id:
        raise SourceError(f"Could not find an arXiv identifier in: {value}")
    return f"https://arxiv.org/html/{paper_id}"


def read_source(value: str, *, timeout: float = 30.0) -> tuple[str, str]:
    """Read a local HTML file or fetch an arXiv paper as HTML."""

    local_path = Path(value).expanduser()
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8"), local_path.resolve().as_uri()

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and "arxiv.org" not in parsed.netloc.lower():
        raise SourceError("The first RPL version supports arXiv URLs and local HTML files.")

    url = normalize_arxiv_url(value)
    request = Request(
        url,
        headers={
            "User-Agent": "RPL/0.3 (+https://github.com/emilsmeznieks/RPL)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=timeout, context=context) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace"), url
    except OSError as exc:
        raise SourceError(f"Could not fetch {url}: {exc}") from exc
