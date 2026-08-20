from __future__ import annotations

import re
import ssl
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi


MODERN_ARXIV_ID = re.compile(
    r"(?<![\w.])(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?(?![\w.])",
    re.I,
)
LEGACY_ARXIV_ID = re.compile(
    r"(?<![\w.-])(?P<archive>[A-Za-z][A-Za-z-]*(?:\.[A-Za-z]{2})?)/"
    r"(?P<number>\d{7})(?P<version>v\d+)?(?!\w)",
    re.I,
)
LEGACY_ARCHIVES = frozenset(
    {
        "adap-org",
        "alg-geom",
        "astro-ph",
        "chao-dyn",
        "cmp-lg",
        "comp-gas",
        "cond-mat",
        "cs",
        "dg-ga",
        "funct-an",
        "gr-qc",
        "hep-ex",
        "hep-lat",
        "hep-ph",
        "hep-th",
        "math",
        "math-ph",
        "nlin",
        "nucl-ex",
        "nucl-th",
        "physics",
        "q-alg",
        "quant-ph",
        "solv-int",
        "stat",
        "supr-con",
    }
)


class SourceError(RuntimeError):
    """Raised when RPL cannot resolve or retrieve a paper source."""


def arxiv_id(value: str) -> str | None:
    modern = MODERN_ARXIV_ID.search(value)
    if modern:
        return modern.group("id") + (modern.group("version") or "").lower()

    for legacy in LEGACY_ARXIV_ID.finditer(value):
        archive = legacy.group("archive")
        if archive.split(".", 1)[0].lower() not in LEGACY_ARCHIVES:
            continue
        return (
            f"{archive}/{legacy.group('number')}"
            f"{(legacy.group('version') or '').lower()}"
        )
    return None


def _validate_arxiv_location(value: str) -> None:
    parsed = urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return
    hostname = (parsed.hostname or "").lower()
    is_arxiv = hostname == "arxiv.org" or hostname.endswith(".arxiv.org")
    if parsed.scheme.lower() not in {"http", "https"} or not is_arxiv:
        raise SourceError("RPL accepts arXiv URLs, arXiv IDs, and local HTML files.")


def normalize_arxiv_url(value: str) -> str:
    """Return the canonical arXiv HTML URL for an ID or arXiv URL."""

    _validate_arxiv_location(value)
    paper_id = arxiv_id(value)
    if not paper_id:
        raise SourceError(f"Could not find an arXiv identifier in: {value}")
    return f"https://arxiv.org/html/{paper_id}"


def read_source(value: str, *, timeout: float = 30.0) -> tuple[str, str]:
    """Read a local HTML file or fetch an arXiv paper as HTML."""

    local_path = Path(value).expanduser()
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8"), local_path.resolve().as_uri()

    url = normalize_arxiv_url(value)
    request = Request(
        url,
        headers={
            "User-Agent": "RPL/0.8 (+https://github.com/emilsmeznieks/RPL)",
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
