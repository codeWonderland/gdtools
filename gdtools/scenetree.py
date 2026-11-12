"""``gdtools tree`` — print the node tree of a Godot scene."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field

from . import tscn
from .style import Style

SCENE_EXTS = (".tscn", ".escn")


@dataclass
class TreeNode:
    name: str
    type: str | None = None
    instance: str | None = None  # res:// path of the instanced scene, if any
    script: str | None = None
    groups: list[str] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)
    children: list["TreeNode"] = field(default_factory=list)
    unique: bool = False
    # "local" = declared in this scene, "instance" = pulled in by --expand,
    # "placeholder" = implied by a parent path we could not resolve.
    origin: str = "local"
    expanded: bool = False
    note: str | None = None

    def walk(self, depth: int = 0):
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "type": self.type}
        if self.instance:
            d["instance"] = self.instance
        if self.script:
            d["script"] = self.script
        if self.groups:
            d["groups"] = self.groups
        if self.unique:
            d["unique_name"] = True
        if self.origin != "local":
            d["origin"] = self.origin
        if self.note:
            d["note"] = self.note
        if self.props:
            d["properties"] = self.props
        d["children"] = [c.to_dict() for c in self.children]
        return d


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


def find_project_root(start: str) -> str | None:
    """Walk upward from ``start`` looking for ``project.godot``."""
    cur = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    while True:
        if os.path.isfile(os.path.join(cur, "project.godot")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def resolve_path(res_path: str, scene_file: str, project_root: str | None) -> str | None:
    """Map a ``res://`` (or relative) path to a file on disk, if it exists."""
    if res_path.startswith("res://"):
        base = project_root or os.path.dirname(os.path.abspath(scene_file))
        candidate = os.path.join(base, res_path[len("res://"):])
    elif res_path.startswith("uid://"):
        return None
    else:
        candidate = os.path.join(os.path.dirname(os.path.abspath(scene_file)), res_path)
    return candidate if os.path.isfile(candidate) else None


_SKIP_PROPS = {"script", "unique_name_in_owner"}


class Builder:
    def __init__(self, expand: bool, project_root: str | None):
        self.expand = expand
        self.project_root = project_root
        self.connections = 0
        self.files_parsed: list[str] = []

    def build(self, path: str, stack: tuple[str, ...] = ()) -> TreeNode:
        scene = tscn.parse_file(path)
        self.files_parsed.append(path)
        if not stack:
            self.scene = scene
            self.connections = len(scene.connections)
        if not scene.nodes:
            raise tscn.ParseError(f"{path}: file has no nodes (is it a resource rather than a scene?)")

        index: dict[str, TreeNode] = {}
        root: TreeNode | None = None
        stack = stack + (os.path.abspath(path),)

        for sec in scene.nodes:
            name = tscn.unquote(sec.attrs.get("name")) or "?"
            parent_attr = tscn.unquote(sec.attrs.get("parent"))

            if parent_attr is None:
                if root is not None:
                    # A second parentless node is malformed; keep it visible.
                    node = self._make(sec, scene, name)
                    node.note = "extra root node"
                    root.children.append(node)
                    continue
                root = self._make(sec, scene, name)
                index["."] = root
                self._maybe_expand(root, ".", index, path, stack)
                continue

            if root is None:
                raise tscn.ParseError(f"{path}:{sec.line}: node '{name}' appears before the root node")

            node_path = name if parent_attr == "." else f"{parent_attr}/{name}"
            existing = index.get(node_path)
            if existing is not None:
                # Override of a node that came from an instanced/inherited scene.
                self._merge(existing, sec, scene)
                continue

            parent = self._lookup_parent(parent_attr, index, root)
            node = self._make(sec, scene, name)
            parent.children.append(node)
            index[node_path] = node
            self._maybe_expand(node, node_path, index, path, stack)

        assert root is not None
        return root

    # -- helpers -----------------------------------------------------------

    def _lookup_parent(self, parent_attr: str, index: dict[str, TreeNode], root: TreeNode) -> TreeNode:
        if parent_attr == ".":
            return root
        if parent_attr in index:
            return index[parent_attr]
        # Parent lives inside an instanced scene we did not expand: create
        # placeholder nodes so the child still shows up in the right place.
        cur = root
        built = ""
        for part in parent_attr.split("/"):
            built = part if not built else f"{built}/{part}"
            nxt = index.get(built)
            if nxt is None:
                nxt = TreeNode(name=part, origin="placeholder")
                cur.children.append(nxt)
                index[built] = nxt
            cur = nxt
        return cur

    def _make(self, sec: tscn.Section, scene: tscn.SceneFile, name: str) -> TreeNode:
        node = TreeNode(name=name)
        self._merge(node, sec, scene)
        return node

    def _merge(self, node: TreeNode, sec: tscn.Section, scene: tscn.SceneFile) -> None:
        a = sec.attrs
        if "type" in a:
            node.type = tscn.unquote(a["type"])
        if "instance" in a:
            ext = scene.resolve_ext(a["instance"])
            node.instance = (ext.path or ext.uid) if ext else a["instance"]
        elif "instance_placeholder" in a:
            node.instance = tscn.unquote(a["instance_placeholder"])
            node.note = "instance placeholder"
        for g in tscn.parse_string_array(a.get("groups")):
            if g not in node.groups:
                node.groups.append(g)
        script_val = sec.props.get("script")
        if script_val is not None:
            if script_val.strip() == "null":
                node.script = None
            else:
                ext = scene.resolve_ext(script_val)
                if ext:
                    node.script = ext.path or ext.uid
                elif "SubResource" in script_val:
                    node.script = "<built-in>"
                else:
                    node.script = script_val
        if sec.props.get("unique_name_in_owner", "").strip() == "true":
            node.unique = True
        for k, v in sec.props.items():
            if k not in _SKIP_PROPS:
                node.props[k] = v

    def _maybe_expand(self, node: TreeNode, node_path: str, index: dict[str, TreeNode], path: str, stack: tuple[str, ...]) -> None:
        if not (self.expand and node.instance and node.instance.endswith(SCENE_EXTS)):
            return
        target = resolve_path(node.instance, path, self.project_root)
        if target is None:
            node.note = "instanced scene not found on disk"
            return
        if os.path.abspath(target) in stack:
            node.note = "recursive instance (not expanded)"
            return
        try:
            sub = self.build(target, stack)
        except (OSError, tscn.ParseError) as exc:
            node.note = f"could not expand: {exc}"
            return
        node.expanded = True
        # Values declared on the instancing node win over the sub-scene root.
        if node.type is None:
            node.type = sub.type
            if node.type is None and sub.instance:
                # Sub-scene itself inherits from another scene (e.g. a .glb).
                node.type = os.path.splitext(os.path.basename(sub.instance))[0]
        if node.script is None:
            node.script = sub.script
        node.groups = sub.groups + [g for g in node.groups if g not in sub.groups]
        node.unique = node.unique or sub.unique
        node.props = {**sub.props, **node.props}
        for child in sub.children:
            node.children.append(child)
            self._register(child, node_path, index)

    def _register(self, node: TreeNode, parent_path: str, index: dict[str, TreeNode]) -> None:
        if node.origin == "local":
            node.origin = "instance"
        p = node.name if parent_path == "." else f"{parent_path}/{node.name}"
        index[p] = node
        for c in node.children:
            self._register(c, p, index)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _short(value: str, width: int = 60) -> str:
    one = " ".join(value.split())
    return one if len(one) <= width else one[: width - 1] + "…"


def render_tree(root: TreeNode, st: Style, max_depth: int | None, show_props: bool, show_paths: bool = True) -> list[str]:
    g = st.glyphs
    lines: list[str] = []

    def label(n: TreeNode) -> str:
        name = ("%" if n.unique else "") + n.name
        if n.origin == "placeholder":
            parts = [st.dim(name), st.dim("(inherited)")]
        else:
            parts = [st.dim(name) if n.origin == "instance" else st.bold(name)]
            if n.type:
                parts.append(st.cyan(f"({n.type})"))
            elif n.instance and not n.expanded:
                parts.append(st.cyan(f"({os.path.splitext(os.path.basename(n.instance))[0]})"))
            elif not n.instance:
                # No type and no instance: an override of a node defined in
                # an inherited or instanced scene.
                parts.append(st.dim("(inherited)"))
        if n.instance:
            parts.append(st.magenta(f"{g['inst']} {n.instance}"))
        if n.script:
            parts.append(st.green(f"{g['script']} {n.script}"))
        if n.groups:
            parts.append(st.yellow("[" + ", ".join(n.groups) + "]"))
        if n.note:
            parts.append(st.red(f"! {n.note}"))
        return " ".join(parts)

    def emit(n: TreeNode, prefix: str, is_last: bool, depth: int, is_root: bool) -> None:
        if is_root:
            lines.append(label(n))
            child_prefix = ""
        else:
            lines.append(st.dim(prefix + (g["last"] if is_last else g["tee"])) + label(n))
            child_prefix = prefix + (g["blank"] if is_last else g["pipe"])
        if show_props and n.props:
            prop_prefix = child_prefix + (g["pipe"] if n.children else g["blank"])
            for k, v in n.props.items():
                lines.append(st.dim(prop_prefix) + st.dim(f"{k} = {_short(v)}"))
        if max_depth is not None and depth >= max_depth:
            if n.children:
                hidden = sum(1 for _ in n.walk()) - 1
                lines.append(st.dim(child_prefix + g["last"] + f"… {hidden} more node{'s' if hidden != 1 else ''}"))
            return
        for i, c in enumerate(n.children):
            emit(c, child_prefix, i == len(n.children) - 1, depth + 1, False)

    emit(root, "", True, 0, True)
    return lines


def summarize(root: TreeNode, builder: Builder) -> dict:
    nodes = list(root.walk())
    types = Counter(n.type or ("<instance>" if n.instance else "<inherited>") for n, _ in nodes)
    return {
        "nodes": len(nodes),
        "max_depth": max(d for _, d in nodes),
        "instanced_scenes": sum(1 for n, _ in nodes if n.instance),
        "scripts": len({n.script for n, _ in nodes if n.script}),
        "groups": sorted({g for n, _ in nodes for g in n.groups}),
        "signal_connections": builder.connections,
        "types": dict(types.most_common()),
    }


def render_summary(scene: tscn.SceneFile, summary: dict, st: Style) -> list[str]:
    ver = f"Godot {scene.godot_major}" if scene.godot_major else "unknown Godot version"
    fmt = scene.format
    top = ", ".join(f"{t} ×{c}" for t, c in list(summary["types"].items())[:6])
    out = [
        "",
        st.bold("Summary") + st.dim(f"  ({ver}, format={fmt})"),
        f"  Nodes: {summary['nodes']}   Max depth: {summary['max_depth']}   "
        f"Instances: {summary['instanced_scenes']}   Scripts: {summary['scripts']}   "
        f"Signal connections: {summary['signal_connections']}",
        f"  Types: {top}" + (" …" if len(summary["types"]) > 6 else ""),
    ]
    if summary["groups"]:
        out.append("  Groups: " + ", ".join(summary["groups"]))
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def add_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "tree",
        aliases=["scene-tree"],
        help="show the node tree of a .tscn scene",
        description="Print the node hierarchy of a Godot .tscn/.escn scene file.",
    )
    p.add_argument("scene", help="path to a .tscn or .escn file")
    p.add_argument("-d", "--depth", type=int, metavar="N", help="only show N levels below the root")
    p.add_argument("-e", "--expand", action="store_true", help="expand instanced scenes inline (resolves res:// via project.godot)")
    p.add_argument("-p", "--props", action="store_true", help="list each node's overridden properties")
    p.add_argument("--json", action="store_true", help="output the tree and summary as JSON")
    p.add_argument("--no-summary", action="store_true", help="hide the summary footer")
    p.add_argument("--ascii", action="store_true", help="use plain ASCII instead of box-drawing characters")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto", help="colorize output (default: auto)")
    p.add_argument("--project", metavar="DIR", help="Godot project root (default: search upward for project.godot)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    path = args.scene
    if not os.path.isfile(path):
        print(f"gdtools: {path}: no such file", file=sys.stderr)
        return 2
    if args.depth is not None and args.depth < 0:
        print("gdtools: --depth must be >= 0", file=sys.stderr)
        return 2
    project_root = os.path.abspath(args.project) if args.project else find_project_root(path)
    builder = Builder(expand=args.expand, project_root=project_root)
    try:
        root = builder.build(path)
    except tscn.ParseError as exc:
        print(f"gdtools: {exc}", file=sys.stderr)
        return 1
    summary = summarize(root, builder)

    if args.json:
        json.dump({"scene": path, "format": builder.scene.format, "root": root.to_dict(), "summary": summary}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    st = Style.for_stream(sys.stdout, args.color, args.ascii)
    lines = render_tree(root, st, args.depth, args.props)
    if not args.no_summary:
        lines += render_summary(builder.scene, summary, st)
    sys.stdout.write("\n".join(lines) + "\n")
    return 0
