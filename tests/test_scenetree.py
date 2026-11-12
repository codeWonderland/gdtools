import io
import json
import os
import unittest
from contextlib import redirect_stdout

from gdtools import cli, tscn
from gdtools.scenetree import Builder, find_project_root

HERE = os.path.dirname(os.path.abspath(__file__))
SCENES = os.path.join(HERE, "fixtures", "project", "scenes")


def scene(name):
    return os.path.join(SCENES, name)


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(list(argv))
    return rc, buf.getvalue()


def build(name, expand=False):
    path = scene(name)
    return Builder(expand, find_project_root(path)).build(path)


class ParserTests(unittest.TestCase):
    def test_header_attributes(self):
        sec = tscn.parse_header('[node name="A B" type="Node2D" parent="." groups=["x", "y z"]]')
        self.assertEqual(sec.tag, "node")
        self.assertEqual(tscn.unquote(sec.attrs["name"]), "A B")
        self.assertEqual(tscn.parse_string_array(sec.attrs["groups"]), ["x", "y z"])

    def test_multiline_property_value(self):
        sf = tscn.parse_file(scene("main.tscn"))
        label = next(n for n in sf.nodes if tscn.unquote(n.attrs["name"]) == "Label")
        self.assertIn("multi-line [world]", label.props["text"])
        self.assertEqual(len(sf.nodes), 7)  # bracket inside the string didn't start a section

    def test_godot3_ext_resource_ids(self):
        sf = tscn.parse_file(scene("godot3.tscn"))
        self.assertEqual(sf.godot_major, 3)
        self.assertEqual(sf.ext_resources["1"].path, "res://scenes/player.gd")

    def test_rejects_non_scene(self):
        with self.assertRaises(tscn.ParseError):
            tscn.parse_text("hello world")


class TreeTests(unittest.TestCase):
    def test_structure(self):
        root = build("main.tscn")
        self.assertEqual(root.name, "Main")
        self.assertEqual(root.script, "res://scenes/main.gd")
        self.assertEqual([c.name for c in root.children], ["World", "Label", "UI"])
        enemy = root.children[0].children[0]
        self.assertEqual(enemy.instance, "res://scenes/enemy.tscn")
        # Override of an instanced child shows up as a child of the instance.
        self.assertEqual([c.name for c in enemy.children], ["Sprite"])

    def test_expand_merges_overrides(self):
        enemy = build("main.tscn", expand=True).children[0].children[0]
        self.assertEqual(enemy.type, "CharacterBody2D")
        self.assertEqual(enemy.groups, ["enemies", "damageable"])
        self.assertEqual([c.name for c in enemy.children], ["Sprite", "Hitbox"])
        sprite = enemy.children[0]
        self.assertTrue(sprite.unique)
        self.assertEqual(sprite.origin, "instance")
        self.assertIn("modulate", sprite.props)

    def test_recursive_instance_is_guarded(self):
        root = build("loop.tscn", expand=True)
        self.assertIn("recursive", root.children[0].note)

    def test_godot3_multiline_header(self):
        root = build("godot3.tscn")
        player = root.children[0]
        self.assertEqual((player.name, player.type), ("Player", "KinematicBody"))
        self.assertEqual(player.groups, ["players"])
        self.assertEqual(player.script, "res://scenes/player.gd")
        self.assertIsNone(root.script)


class CliTests(unittest.TestCase):
    def test_text_output(self):
        rc, out = run_cli("tree", scene("main.tscn"), "--color", "never", "--ascii")
        self.assertEqual(rc, 0)
        self.assertIn("Main (Node2D) script: res://scenes/main.gd", out)
        self.assertIn("`-- UI (CanvasLayer)", out)
        self.assertIn("Signal connections: 1", out)

    def test_depth_limit(self):
        rc, out = run_cli("tree", scene("main.tscn"), "--color", "never", "-d", "1", "--no-summary")
        self.assertNotIn("Score", out)
        self.assertIn("1 more node", out)

    def test_json(self):
        rc, out = run_cli("tree", scene("main.tscn"), "--json", "-e")
        data = json.loads(out)
        self.assertEqual(data["root"]["name"], "Main")
        self.assertEqual(data["summary"]["nodes"], 8)

    def test_missing_file(self):
        rc, _ = run_cli("tree", scene("nope.tscn"))
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
