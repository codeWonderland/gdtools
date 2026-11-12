"""Entry point for the ``gdtools`` command.

Each tool lives in its own module and exposes ``add_parser(subparsers)``;
register new tools in ``TOOLS`` below.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, scenetree

TOOLS = [scenetree]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdtools",
        description="Command-line tools for Godot projects.",
        epilog="Run 'gdtools <command> --help' for details on a command.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"gdtools {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for tool in TOOLS:
        tool.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except BrokenPipeError:
        # e.g. `gdtools tree big.tscn | head`
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
