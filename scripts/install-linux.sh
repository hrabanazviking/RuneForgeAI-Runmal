#!/usr/bin/env bash
set -euo pipefail

REF="${RUNMAL_REF:-main}"
REPO="hrabanazviking/RuneForgeAI-Runmal"
INSTALL_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/runmal-app"
VENV="$INSTALL_ROOT/venv"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
TMP="$(mktemp -d -t runmal-install.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nRúnmál installation failed: %s\n' "$1" >&2; exit 1; }

find_python() {
  local candidate version
  for candidate in python3.15 python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      version="$($candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      case "$version" in
        3.12|3.13|3.14|3.15) command -v "$candidate"; return 0 ;;
      esac
    fi
  done
  return 1
}

PYTHON="$(find_python || true)"
if [[ -z "$PYTHON" ]]; then
  fail "Python 3.12 or newer is required for the source installer. For a no-dependency install, use the Rúnmál desktop package for your platform."
fi

command -v curl >/dev/null 2>&1 || fail "curl is required for this source installer."
command -v unzip >/dev/null 2>&1 || fail "unzip is required for this source installer."

# This installer is architecture-neutral by design: it installs from
# source and pip resolves the correct wheels for the running machine
# (x86_64 and aarch64 alike). Report the architecture it detected so
# the log always shows which machine shape was served.
say "Detected architecture: $(uname -m)"

say "Downloading Rúnmál"
ARCHIVE="$TMP/runmal.zip"
curl -fL "https://github.com/$REPO/archive/refs/heads/$REF.zip" -o "$ARCHIVE"
unzip -q "$ARCHIVE" -d "$TMP/source"
SOURCE="$(find "$TMP/source" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -f "$SOURCE/pyproject.toml" ]] || fail "Downloaded archive is missing pyproject.toml."

say "Installing Rúnmál into a private environment"
mkdir -p "$INSTALL_ROOT" "$BIN_DIR" "$APPLICATIONS_DIR" "$ICON_DIR"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV" || fail "Could not create the private Python environment. Your distribution may need its python3-venv package."
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade "$SOURCE"

cat > "$BIN_DIR/runmal-launcher" <<EOF
#!/usr/bin/env bash
if [[ \$# -eq 0 ]]; then
  set -- open
fi
exec "$VENV/bin/python" -m runmal.launcher "\$@"
EOF
chmod +x "$BIN_DIR/runmal-launcher"

cat > "$APPLICATIONS_DIR/runmal.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Rúnmál
Comment=Sovereign local AI chat app
Exec=$VENV/bin/python -m runmal.launcher open
Icon=runmal
Terminal=false
Categories=Utility;Education;
StartupNotify=true
Actions=ControlCenter;

[Desktop Action ControlCenter]
Name=Rúnmál Control Center
Exec=$VENV/bin/python -m runmal.launcher control
EOF
chmod 644 "$APPLICATIONS_DIR/runmal.desktop"

if [[ -f "$SOURCE/docs/images/runmal-emblem.png" ]]; then
  cp "$SOURCE/docs/images/runmal-emblem.png" "$ICON_DIR/runmal.png"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

say "Checking the installation"
"$VENV/bin/python" -m runmal.launcher doctor || true

printf '\nRúnmál is installed. Open it from your application menu.\n'
nohup "$VENV/bin/python" -m runmal.launcher open >/dev/null 2>&1 &
