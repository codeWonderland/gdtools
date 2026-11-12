"""Parser for Godot's text scene/resource format (.tscn / .escn / .tres).

Handles both Godot 3 (format=2) and Godot 4 (format=3+) files. Only the
standard library is used so the tool runs anywhere Python 3 does, including
Termux on Android.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EXT_REF_RE = re.compile(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)')
_SUB_REF_RE = re.compile(r'SubResource\(\s*"?([^")\s]+)"?\s*\)')
_PROP_RE = re.compile(r"^([A-Za-z_][\w/:.\-]*)\s*=\s*(.*)$")


class ParseError(Exception):
    """Raised when a file cannot be parsed as a Godot text resource."""


@dataclass
class Section:
    """One ``[tag key=value ...]`` block plus the properties under it."""

    tag: str
    attrs: dict[str, str]
    props: dict[str, str] = field(default_factory=dict)
    line: int = 0


@dataclass
class ExtResource:
    id: str
    type: str
    path: str | None
    uid: str | None


@dataclass
class SceneFile:
    path: str
    header: Section
    ext_resources: dict[str, ExtResource]
    sub_resources: list[Section]
    nodes: list[Section]
    connections: list[Section]

    @property
    def format(self) -> int | None:
        raw = self.header.attrs.get("format")
        return int(raw) if raw and raw.isdigit() else None

    @property
    def godot_major(self) -> int | None:
        fmt = self.format
        if fmt is None:
            return None
        return 4 if fmt >= 3 else 3

    def resolve_ext(self, value: str | None) -> ExtResource | None:
        """Return the ExtResource referenced by an ``ExtResource(...)`` value."""
        if not value:
            return None
        m = _EXT_REF_RE.search(value)
        if not m:
            return None
        return self.ext_resources.get(m.group(1))


def unquote(value: str | None) -> str | None:
    """Turn a Godot string literal (``"foo"`` / ``&"foo"``) into plain text."""
    if value is None:
        return None
    v = value.strip()
    if v.startswith(("&", "^")) and len(v) > 1 and v[1] == '"':
        v = v[1:]
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        body = v[1:-1]
        return (
            body.replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\\\", "\\")
        )
    return v


def parse_string_array(value: str | None) -> list[str]:
    """Parse ``["a", "b"]`` / ``PackedStringArray("a")`` into a list."""
    if not value:
        return []
    return [unquote(m.group(0)) or "" for m in re.finditer(r'"(?:\\.|[^"\\])*"', value)]


def _scan_value(text: str, i: int, stop: str) -> int:
    """Return the index where a value starting at ``i`` ends.

    A value ends at the first character in ``stop`` that is outside any
    string literal and at bracket depth zero.
    """
    depth = 0
    in_str = False
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and c in stop:
            return i
        i += 1
    return i


def parse_header(line: str, lineno: int = 0) -> Section:
    """Parse a section header such as ``[node name="A" type="Node2D"]``."""
    text = line.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ParseError(f"line {lineno}: not a section header: {line!r}")
    body = text[1:-1].strip()
    m = re.match(r"[\w]+", body)
    if not m:
        raise ParseError(f"line {lineno}: missing section tag: {line!r}")
    tag = m.group(0)
    i = m.end()
    attrs: dict[str, str] = {}
    n = len(body)
    while i < n:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        km = re.match(r"[\w/:.\-]+", body[i:])
        if not km:
            raise ParseError(f"line {lineno}: bad attribute in header: {line!r}")
        key = km.group(0)
        i += km.end()
        while i < n and body[i].isspace():
            i += 1
        if i < n and body[i] == "=":
            i += 1
            while i < n and body[i].isspace():
                i += 1
            end = _scan_value(body, i, " \t")
            attrs[key] = body[i:end].strip()
            i = end
        else:
            attrs[key] = ""
    return Section(tag=tag, attrs=attrs, line=lineno)


def _depth_delta(text: str, in_str: bool) -> tuple[int, bool]:
    """Bracket depth change across ``text`` and whether a string is left open."""
    delta = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "([{":
            delta += 1
        elif c in ")]}":
            delta -= 1
        i += 1
    return delta, in_str


def parse_text(text: str, path: str = "<string>") -> SceneFile:
    """Parse the contents of a .tscn/.escn/.tres file."""
    sections: list[Section] = []
    current: Section | None = None
    pending_key: str | None = None
    pending_val: list[str] = []
    depth = 0
    in_str = False

    def flush() -> None:
        nonlocal pending_key, pending_val
        if current is not None and pending_key is not None:
            current.props[pending_key] = "\n".join(pending_val).strip()
        pending_key, pending_val = None, []

    header_buf: list[str] = []
    header_line = 0
    header_depth = 0
    header_str = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r")
        # Godot 3 may split a header across lines, e.g. ``groups=[\n"a",\n]]``.
        if header_buf:
            header_buf.append(line.strip())
            d, header_str = _depth_delta(line, header_str)
            header_depth += d
            if header_depth <= 0 and not header_str:
                current = parse_header(" ".join(header_buf), header_line)
                sections.append(current)
                header_buf = []
            continue
        # Inside a multi-line value: keep appending until brackets balance.
        if pending_key is not None and (depth > 0 or in_str):
            pending_val.append(line)
            d, in_str = _depth_delta(line, in_str)
            depth += d
            if depth <= 0 and not in_str:
                depth = 0
                flush()
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if re.match(r"\[\w+[\s\]]", stripped):
            flush()
            d, s_open = _depth_delta(stripped, False)
            if d > 0 or s_open:
                header_buf, header_line, header_depth, header_str = [stripped], lineno, d, s_open
                continue
            current = parse_header(stripped, lineno)
            sections.append(current)
            continue

        pm = _PROP_RE.match(stripped)
        if pm and current is not None:
            flush()
            pending_key = pm.group(1)
            pending_val = [pm.group(2)]
            depth, in_str = _depth_delta(pm.group(2), False)
            if depth <= 0 and not in_str:
                depth = 0
                flush()
            continue
        # Anything else (stray text) is ignored rather than fatal; Godot
        # files in the wild occasionally contain odd whitespace/comments.
    flush()
    if header_buf:
        raise ParseError(f"{path}:{header_line}: unterminated section header")

    if not sections:
        raise ParseError(f"{path}: no sections found (is this a Godot text resource?)")
    header = sections[0]
    if header.tag not in ("gd_scene", "gd_resource"):
        raise ParseError(f"{path}: expected [gd_scene] header, found [{header.tag}]")

    ext: dict[str, ExtResource] = {}
    subs: list[Section] = []
    nodes: list[Section] = []
    conns: list[Section] = []
    for sec in sections[1:]:
        if sec.tag == "ext_resource":
            rid = unquote(sec.attrs.get("id")) or ""
            ext[rid] = ExtResource(
                id=rid,
                type=unquote(sec.attrs.get("type")) or "",
                path=unquote(sec.attrs.get("path")),
                uid=unquote(sec.attrs.get("uid")),
            )
        elif sec.tag == "sub_resource":
            subs.append(sec)
        elif sec.tag == "node":
            nodes.append(sec)
        elif sec.tag == "connection":
            conns.append(sec)
    return SceneFile(path=path, header=header, ext_resources=ext, sub_resources=subs, nodes=nodes, connections=conns)


def parse_file(path: str) -> SceneFile:
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except UnicodeDecodeError as exc:
        raise ParseError(f"{path}: not a text file (binary .scn is not supported)") from exc
    return parse_text(text, path)
