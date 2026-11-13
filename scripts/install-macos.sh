#!/usr/bin/env bash
set -euo pipefail

REF="${RUNMAL_REF:-main}"
REPO="hrabanazviking/RuneForgeAI-Runmal"
INSTALL_ROOT="$HOME/Library/Application Support/Runmal"
VENV="$INSTALL_ROOT/venv"
APP_DIR="$HOME/Applications"
APP="$APP_DIR/Rúnmál.app"
TMP="$(mktemp -d -t runmal-install)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nRúnmál installation failed: %s\n' "$1" >&2; exit 1; }

find_python() {
  local candidate version
  for candidate in python3.13 python3.12 python3; do
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
  fail "Python 3.12 or newer is required for the source installer. For the no-dependency experience, use the Rúnmál DMG."
fi

say "Downloading Rúnmál"
curl -fL "https://github.com/$REPO/archive/refs/heads/$REF.zip" -o "$TMP/runmal.zip"
ditto -x -k "$TMP/runmal.zip" "$TMP/source"
SOURCE="$(find "$TMP/source" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -f "$SOURCE/pyproject.toml" ]] || fail "Downloaded archive is missing pyproject.toml."
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$SOURCE/pyproject.toml" | head -n 1)"
[[ -n "$VERSION" ]] || fail "Could not read the Rúnmál version from the downloaded source."

say "Installing Rúnmál into a private environment"
mkdir -p "$INSTALL_ROOT" "$APP_DIR"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade "$SOURCE"

say "Creating the Rúnmál application"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Rúnmál</string>
  <key>CFBundleDisplayName</key><string>Rúnmál</string>
  <key>CFBundleIdentifier</key><string>dev.runmal.desktop</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
EOF
cat > "$APP/Contents/MacOS/runmal" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" -m runmal.launcher open
EOF
chmod +x "$APP/Contents/MacOS/runmal"

say "Checking the installation"
"$VENV/bin/python" -m runmal.launcher doctor || true

printf '\nRúnmál is installed in ~/Applications.\n'
open "$APP"
