#!/usr/bin/env bash
# Rúnmál local Linux package builder
# Builds entirely on the current Linux machine. No GitHub Actions or hosted CI.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This builder must be run on Linux." >&2
  exit 1
fi

PYTHON=""
for candidate in python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "Python 3.12 or newer is required to build Rúnmál locally." >&2
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required to create the Debian package." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
  echo "Python tkinter is required. On Debian/Ubuntu/Kubuntu install python3-tk, then run this builder again." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)
    echo "Unsupported Debian package architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

BUILD_VENV="$REPO_ROOT/.runmal-build-venv"
if [[ ! -x "$BUILD_VENV/bin/python" ]]; then
  echo "Creating isolated local build environment..."
  "$PYTHON" -m venv "$BUILD_VENV"
fi

VPY="$BUILD_VENV/bin/python"
PYINSTALLER="$BUILD_VENV/bin/pyinstaller"

echo "Installing Rúnmál build dependencies locally..."
"$VPY" -m pip install --upgrade pip
"$VPY" -m pip install -e . pyinstaller

VERSION="$($VPY -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"

echo "Building standalone Linux application..."
"$PYINSTALLER" --noconfirm --clean --onedir \
  --name runmal \
  --hidden-import tkinter \
  --hidden-import tkinter.messagebox \
  --hidden-import tkinter.scrolledtext \
  --hidden-import aiosqlite \
  --collect-all sqlite_vec \
  --collect-all runmal \
  src/runmal/launcher/frozen_entry.py

RUNMAL_BIN="$REPO_ROOT/dist/runmal/runmal"
if [[ ! -x "$RUNMAL_BIN" ]]; then
  echo "PyInstaller did not create dist/runmal/runmal" >&2
  exit 1
fi

echo "Smoke-testing launcher..."
"$RUNMAL_BIN" status

echo "Smoke-testing local server..."
PORT=18098
LOG="$(mktemp)"
"$RUNMAL_BIN" _serve --port "$PORT" >"$LOG" 2>&1 &
PID=$!
cleanup_server() {
  kill "$PID" 2>/dev/null || true
  rm -f "$LOG"
}
trap cleanup_server EXIT

READY=0
for _ in $(seq 1 100); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.2
done

if [[ "$READY" -ne 1 ]]; then
  cat "$LOG" >&2
  echo "Frozen Linux server failed its /healthz check." >&2
  exit 1
fi
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - EXIT
rm -f "$LOG"

PACKAGE_ROOT="$(mktemp -d)"
trap 'rm -rf "$PACKAGE_ROOT"' EXIT
mkdir -p \
  "$PACKAGE_ROOT/DEBIAN" \
  "$PACKAGE_ROOT/opt/runmal" \
  "$PACKAGE_ROOT/usr/share/applications" \
  "$PACKAGE_ROOT/usr/share/icons/hicolor/512x512/apps"

cp -a dist/runmal/. "$PACKAGE_ROOT/opt/runmal/"
cp packaging/linux/runmal.desktop "$PACKAGE_ROOT/usr/share/applications/runmal.desktop"
cp docs/images/runmal-emblem.png "$PACKAGE_ROOT/usr/share/icons/hicolor/512x512/apps/runmal.png"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: runmal
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Volmarr
Description: Rúnmál sovereign local AI chat application
EOF

OUTPUT="$REPO_ROOT/runmal_${VERSION}_${ARCH}.deb"
echo "Building Debian package locally..."
dpkg-deb --build "$PACKAGE_ROOT" "$OUTPUT"

HASH="$(sha256sum "$OUTPUT" | awk '{print $1}')"
echo
echo "Rúnmál Linux package built successfully."
echo "File: $OUTPUT"
echo "SHA-256: $HASH"
echo
echo "This build was produced locally on this Linux machine. No GitHub Actions were used."
