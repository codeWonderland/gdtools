"""Terminal colors and tree glyphs."""

from __future__ import annotations

import os

_UNICODE = {"tee": "├── ", "last": "└── ", "pipe": "│   ", "blank": "    ", "inst": "⇢", "script": "⚙"}
_ASCII = {"tee": "|-- ", "last": "`-- ", "pipe": "|   ", "blank": "    ", "inst": "->", "script": "script:"}


class Style:
    def __init__(self, color: bool, ascii_only: bool):
        self.color = color
        self.glyphs = _ASCII if ascii_only else _UNICODE

    @classmethod
    def for_stream(cls, stream, mode: str = "auto", ascii_only: bool = False) -> "Style":
        if mode == "always":
            color = True
        elif mode == "never":
            color = False
        else:
            color = (
                hasattr(stream, "isatty")
                and stream.isatty()
                and "NO_COLOR" not in os.environ
                and os.environ.get("TERM") != "dumb"
            )
        if not ascii_only:
            enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
            ascii_only = enc not in ("", "utf8", "utf16", "utf32") and not enc.startswith("utf")
        return cls(color, ascii_only)

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def bold(self, t: str) -> str:
        return self._wrap("1", t)

    def dim(self, t: str) -> str:
        return self._wrap("2", t)

    def red(self, t: str) -> str:
        return self._wrap("31", t)

    def green(self, t: str) -> str:
        return self._wrap("32", t)

    def yellow(self, t: str) -> str:
        return self._wrap("33", t)

    def magenta(self, t: str) -> str:
        return self._wrap("35", t)

    def cyan(self, t: str) -> str:
        return self._wrap("36", t)
