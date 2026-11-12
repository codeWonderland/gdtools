#!/usr/bin/env sh
# gdtools installer — works on Linux desktops and Android (Termux).
#
#   curl -fsSL https://raw.githubusercontent.com/codeWonderland/gdtools/main/install.sh | sh
#
# Options (pass after `sh -s --` when piping):
#   --uninstall   remove gdtools
#   --ref REF     install a branch/tag other than main
set -eu

REPO="codeWonderland/gdtools"
REF="main"
ACTION="install"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gdtools"

while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) ACTION="uninstall" ;;
    --ref) shift; REF="$1" ;;
    -h|--help) sed -n '2,9p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

is_termux() { [ -n "${TERMUX_VERSION:-}" ] || case "${PREFIX:-}" in *com.termux*) true ;; *) false ;; esac; }

if is_termux; then
  BIN_DIR="${PREFIX}/bin"
else
  BIN_DIR="$HOME/.local/bin"
fi

if [ "$ACTION" = "uninstall" ]; then
  if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package gdtools"; then
    pipx uninstall gdtools
  fi
  rm -rf "$DATA_DIR"
  if [ -f "$BIN_DIR/gdtools" ] && grep -q "installed by gdtools install.sh" "$BIN_DIR/gdtools" 2>/dev/null; then
    rm -f "$BIN_DIR/gdtools"
  fi
  say "gdtools removed"
  exit 0
fi

# Python 3.8+ is the only requirement.
if ! command -v python3 >/dev/null 2>&1; then
  if is_termux; then
    say "Installing Python with pkg"
    pkg install -y python
  else
    die "python3 not found. Install it first (e.g. 'sudo apt install python3')."
  fi
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || die "gdtools needs Python 3.8 or newer"

# Use this checkout when run locally, otherwise download from GitHub.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || echo "")
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -d "$SCRIPT_DIR/gdtools" ]; then
  SRC_DIR="$SCRIPT_DIR"
else
  URL="https://github.com/$REPO/archive/$REF.tar.gz"
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  say "Downloading $URL"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$TMP/src.tar.gz"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP/src.tar.gz" "$URL"
  else
    die "need curl or wget to download gdtools"
  fi
  tar -xzf "$TMP/src.tar.gz" -C "$TMP"
  SRC_DIR=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
fi

# Prefer pipx when present (easy upgrades); otherwise do a plain install.
# gdtools has no dependencies, so it needs neither pip nor a virtualenv.
if command -v pipx >/dev/null 2>&1 && [ "${GDTOOLS_NO_PIPX:-}" = "" ]; then
  say "Installing with pipx"
  pipx install --force "$SRC_DIR"
  say "Done. Run: gdtools --help"
  exit 0
fi

say "Installing to $DATA_DIR"
rm -rf "$DATA_DIR/lib"
mkdir -p "$DATA_DIR/lib" "$BIN_DIR"
cp -R "$SRC_DIR/gdtools" "$DATA_DIR/lib/gdtools"
find "$DATA_DIR/lib" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

rm -f "$BIN_DIR/gdtools"
cat > "$BIN_DIR/gdtools" <<LAUNCHER
#!/bin/sh
# gdtools launcher (installed by gdtools install.sh)
PYTHONPATH="$DATA_DIR/lib\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m gdtools "\$@"
LAUNCHER
chmod +x "$BIN_DIR/gdtools"

say "Installed: $BIN_DIR/gdtools"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) printf '\n%s is not on your PATH. Add this to your shell profile:\n  export PATH="%s:$PATH"\n\n' "$BIN_DIR" "$BIN_DIR" ;;
esac
say "Run: gdtools --help"
