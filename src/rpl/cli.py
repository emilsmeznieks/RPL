from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .digest import build_digest
from .parser import parse_arxiv_html
from .render import render_json, render_markdown
from .source import SourceError, read_source


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "paper"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpl",
        description="Turn an arXiv paper into focused human and agent-readable knowledge.",
    )
    parser.add_argument("--version", action="version", version=f"RPL {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    learn = commands.add_parser("learn", help="extract a learning card from an arXiv paper")
    learn.add_argument("source", help="arXiv URL, arXiv ID, or local HTML file")
    learn.add_argument(
        "-o",
        "--output",
        default="rpl-output",
        help="output directory (default: rpl-output)",
    )
    learn.add_argument(
        "--format",
        choices=("all", "markdown", "json"),
        default="all",
        help="output format (default: all)",
    )
    learn.add_argument("--stdout", action="store_true", help="print the selected output instead of writing files")
    learn.add_argument("--timeout", type=float, default=30.0, help="download timeout in seconds")
    return parser


def learn(args: argparse.Namespace) -> int:
    try:
        html, source_url = read_source(args.source, timeout=args.timeout)
        paper = parse_arxiv_html(html, source_url)
    except (SourceError, OSError, UnicodeError) as exc:
        print(f"rpl: {exc}", file=sys.stderr)
        return 1

    digest = build_digest(paper)
    markdown = render_markdown(paper, digest)
    json_output = render_json(paper, digest)

    if args.stdout:
        if args.format == "json":
            print(json_output, end="")
        elif args.format == "markdown":
            print(markdown, end="")
        else:
            print(markdown, end="")
            print("\n<!-- RPL JSON -->\n")
            print(json_output, end="")
        return 0

    destination = Path(args.output) / safe_name(paper.paper_id)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if args.format in ("all", "markdown"):
        path = destination / "paper.md"
        path.write_text(markdown, encoding="utf-8")
        written.append(path)
    if args.format in ("all", "json"):
        path = destination / "paper.json"
        path.write_text(json_output, encoding="utf-8")
        written.append(path)

    print(f"RPL extracted {paper.title}")
    for path in written:
        print(f"  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "learn":
        return learn(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

