# gdtools

Command-line tools for [Godot](https://godotengine.org) projects. They run in any Linux terminal, including **Android via Termux**.

gdtools is pure Python with **no dependencies**. It reads Godot's text formats (`.tscn`, `.escn`) directly, so you don't need the Godot editor or engine to use it.

| Command        | What it does                                   |
| -------------- | ---------------------------------------------- |
| `gdtools tree` | Visualize the node tree of a scene             |

More tools are planned.

---

## Install

You need **Python 3.8+**. The installer also needs `curl` or `wget`.

### Linux (Debian/Ubuntu, Fedora, Arch, …)

```sh
curl -fsSL https://raw.githubusercontent.com/codeWonderland/gdtools/main/install.sh | sh
```

The installer uses `pipx` if you have it. Otherwise it copies gdtools to `~/.local/share/gdtools` and puts a `gdtools` launcher in `~/.local/bin`. This works on distros that block system-wide `pip install` (PEP 668), and you don't need `python3-venv`.

If the installer says `~/.local/bin` isn't on your `PATH`, add this line to `~/.bashrc` (or `~/.zshrc`):

```sh
export PATH="$HOME/.local/bin:$PATH"
```

### Android (Termux)

Install [Termux from F-Droid](https://f-droid.org/packages/com.termux/). The Play Store build is outdated. Then run:

```sh
pkg update
pkg install python curl
curl -fsSL https://raw.githubusercontent.com/codeWonderland/gdtools/main/install.sh | sh
```

On Termux the launcher goes in `$PREFIX/bin`, which is already on your `PATH`.

To read projects in your phone's shared storage (for example, a Godot project you synced to the device), give Termux storage access once:

```sh
termux-setup-storage
gdtools tree ~/storage/shared/Godot/my-game/main.tscn
```

### Other install methods

From a clone of this repo:

```sh
git clone https://github.com/codeWonderland/gdtools.git
cd gdtools
./install.sh
```

With pipx or pip:

```sh
pipx install git+https://github.com/codeWonderland/gdtools.git
# or, inside a virtualenv:
pip install git+https://github.com/codeWonderland/gdtools.git
```

Run it straight from a checkout without installing:

```sh
python3 -m gdtools tree path/to/scene.tscn
```

### Update / uninstall

To update, run the install command again. To uninstall:

```sh
curl -fsSL https://raw.githubusercontent.com/codeWonderland/gdtools/main/install.sh | sh -s -- --uninstall
```

(If you installed with pipx, use `pipx uninstall gdtools`.)

---

## `gdtools tree` — scene tree visualizer

```sh
gdtools tree <scene.tscn> [options]
```

Example:

```
$ gdtools tree scenes/main.tscn
Main (Node2D) ⚙ res://scenes/main.gd
├── World (Node2D)
│   └── Enemy (enemy) ⇢ res://scenes/enemy.tscn
│       └── Sprite (inherited)
├── Label (Label)
└── UI (CanvasLayer)
    └── Score (Label)

Summary  (Godot 4, format=3)
  Nodes: 7   Max depth: 3   Instances: 1   Scripts: 1   Signal connections: 1
  Types: Node2D ×2, Label ×2, <instance> ×1, <inherited> ×1, CanvasLayer ×1
```

Add `--expand` to pull instanced scenes into the tree:

```
$ gdtools tree scenes/main.tscn --expand --props --no-summary
Main (Node2D) ⚙ res://scenes/main.gd
├── World (Node2D)
│   └── Enemy (CharacterBody2D) ⇢ res://scenes/enemy.tscn ⚙ res://scenes/enemy.gd [enemies, damageable]
│       │   speed = 120.0
│       │   position = Vector2(10, 20)
│       ├── %Sprite (Sprite2D)
│       │       modulate = Color(1, 0, 0, 1)
│       └── Hitbox (CollisionShape2D)
│               shape = SubResource("CircleShape2D_1")
├── Label (Label)
│       text = "Hello multi-line [world]"
└── UI (CanvasLayer)
    └── Score (Label)
            text = "0"
```

### Reading the output

| Marker              | Meaning                                                              |
| ------------------- | -------------------------------------------------------------------- |
| `Name (Type)`       | Node name and class                                                  |
| `%Name`             | Node has a scene-unique name (`unique_name_in_owner`)                |
| `⇢ res://…`         | Node is an instance of another scene or model (`.tscn`, `.glb`, …)   |
| `⚙ res://…`         | Attached script (`<built-in>` for embedded scripts)                  |
| `[a, b]`            | Groups the node belongs to                                           |
| `(inherited)`       | Node comes from an instanced/inherited scene and is only overridden here |
| dimmed name         | Node was pulled in by `--expand`                                      |
| `! …`               | Warning, e.g. a missing or recursive instance                         |

### Options

| Option                      | Description                                                               |
| --------------------------- | ------------------------------------------------------------------------- |
| `-e`, `--expand`            | Expand instanced `.tscn` scenes inline, recursively. `res://` paths are resolved from the nearest `project.godot`. |
| `-d N`, `--depth N`         | Only show N levels below the root. Deeper branches collapse to `… N more nodes`. |
| `-p`, `--props`             | List the properties each node sets or overrides                           |
| `--json`                    | Output the tree and summary as JSON (for scripts, `jq`, etc.)             |
| `--no-summary`              | Hide the summary footer                                                   |
| `--ascii`                   | Use plain ASCII (`\|--`, `` `-- ``) instead of box-drawing characters     |
| `--color auto\|always\|never` | Color output. Default `auto`: color on a terminal only, and `NO_COLOR` is respected. |
| `--project DIR`             | Godot project root to use instead of searching upward for `project.godot` |

`scene-tree` is an alias for `tree`.

### More examples

```sh
# Quick overview of a big level: just the top two levels
gdtools tree levels/world.tscn -d 2

# Everything, fully expanded, paged with colors kept
gdtools tree main.tscn -e -p --color always | less -R

# List every node type used in a scene
gdtools tree main.tscn -e --json | jq '.summary.types'

# Find every node with an attached script
gdtools tree main.tscn -e --json | jq -r '.. | objects | select(.script?) | "\(.name)\t\(.script)"'
```

### Compatibility

- Godot 4.x scenes (`format=3` and later) and Godot 3.x scenes (`format=2`).
- Inherited scenes, instanced scenes, editable-children overrides, groups, unique names, and multi-line property values are all handled.
- Binary `.scn` files aren't supported. Save the scene as `.tscn` to inspect it.
- Instances of imported models (`.glb`, `.gltf`, `.blend`, …) are shown as a single node. They aren't expanded, because their node tree only exists after Godot imports them.

---

## Development

```sh
git clone https://github.com/codeWonderland/gdtools.git
cd gdtools
python3 -m unittest discover -s tests -t .
python3 -m gdtools tree tests/fixtures/project/scenes/main.tscn -e
```

Code layout:

- `gdtools/tscn.py`: parser for Godot's text scene format
- `gdtools/scenetree.py`: the `tree` command (builds and renders the node tree)
- `gdtools/style.py`: colors and tree glyphs
- `gdtools/cli.py`: entry point and command registry

To add a tool, create a module with an `add_parser(subparsers)` function that registers its subcommand and sets `func`. Then add the module to `TOOLS` in `gdtools/cli.py`.

## License

MIT. See [LICENSE](LICENSE).
