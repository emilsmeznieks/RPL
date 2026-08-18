from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import __version__
from .parser import PaperParseError
from .service import analyze_source, write_analysis
from .source import SourceError


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


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
        choices=("all", "html", "markdown", "json"),
        default="all",
        help="output format (default: all)",
    )
    learn.add_argument(
        "--stdout",
        action="store_true",
        help="print the selected output instead of writing files",
    )
    learn.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="download timeout in seconds",
    )

    mcp = commands.add_parser("mcp", help="run RPL as a local MCP server")
    mcp.add_argument(
        "-o",
        "--output",
        default=str(Path.home() / "RPL"),
        help="artifact directory (default: ~/RPL)",
    )
    mcp.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="paper download timeout in seconds",
    )
    return parser


def learn(args: argparse.Namespace) -> int:
    try:
        analysis = analyze_source(args.source, timeout=args.timeout)
    except (PaperParseError, SourceError, OSError, UnicodeError) as exc:
        print(f"rpl: {exc}", file=sys.stderr)
        return 1

    if args.stdout:
        if args.format == "json":
            print(analysis.json, end="")
        elif args.format == "html":
            print(analysis.html, end="")
        elif args.format == "markdown":
            print(analysis.markdown, end="")
        else:
            print(analysis.markdown, end="")
            print("\n<!-- RPL JSON -->\n")
            print(analysis.json, end="")
            print("\n<!-- RPL HTML -->\n")
            print(analysis.html, end="")
        return 0

    formats = (
        ("markdown", "json", "html") if args.format == "all" else (args.format,)
    )
    try:
        written = write_analysis(analysis, args.output, formats)
    except OSError as exc:
        print(f"rpl: Could not write output: {exc}", file=sys.stderr)
        return 1

    print(f"RPL extracted {analysis.paper.title}")
    for path in written:
        print(f"  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "learn":
        return learn(args)
    if args.command == "mcp":
        try:
            from .mcp_server import run_server
        except ModuleNotFoundError as exc:
            if exc.name != "mcp" and not (exc.name or "").startswith("mcp."):
                raise
            print(
                'rpl: MCP support is not installed. Run: pip install "rpl-research[mcp]"',
                file=sys.stderr,
            )
            return 1
        run_server(args.output, timeout=args.timeout)
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
