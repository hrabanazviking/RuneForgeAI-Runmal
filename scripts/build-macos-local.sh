#!/usr/bin/env bash
# Rúnmál local macOS package builder
# Builds entirely on the current Mac. No GitHub Actions or hosted CI.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This builder must be run on macOS." >&2
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

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "hdiutil is required to create the macOS DMG." >&2
  exit 1
fi

BUILD_VENV="$REPO_ROOT/.runmal-build-venv"
if [[ ! -x "$BUILD_VENV/bin/python" ]]; then
  echo "Creating isolated local build environment..."
  "$PYTHON" -m venv "$BUILD_VENV"
fi

VPY="$BUILD_VENV/bin/python"
PYINSTALLER="$BUILD_VENV/bin/pyinstaller"

echo "Installing Rúnmál build dependencies locally..."
"$VPY" -m pip install --upgrade pip
"$VPY" -m pip install -e . pyinstaller pillow

VERSION="$($VPY -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"

case "$(uname -m)" in
  arm64) LABEL="Apple-Silicon" ;;
  x86_64) LABEL="Intel" ;;
  *)
    echo "Unsupported macOS architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

echo "Building standalone macOS application..."
"$PYINSTALLER" --noconfirm --clean --windowed \
  --name Runmal \
  --icon docs/images/runmal-emblem.png \
  --hidden-import tkinter \
  --hidden-import tkinter.messagebox \
  --hidden-import tkinter.scrolledtext \
  --hidden-import aiosqlite \
  --collect-all sqlite_vec \
  --collect-all runmal \
  src/runmal/launcher/frozen_entry.py

RUNMAL_BIN="$REPO_ROOT/dist/Runmal.app/Contents/MacOS/Runmal"
if [[ ! -x "$RUNMAL_BIN" ]]; then
  echo "PyInstaller did not create dist/Runmal.app" >&2
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
  echo "Frozen macOS server failed its /healthz check." >&2
  exit 1
fi
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - EXIT
rm -f "$LOG"

DMG_ROOT="$(mktemp -d)"
trap 'rm -rf "$DMG_ROOT"' EXIT
cp -R dist/Runmal.app "$DMG_ROOT/Runmal.app"
ln -s /Applications "$DMG_ROOT/Applications"

OUTPUT="$REPO_ROOT/Runmal-macOS-${LABEL}.dmg"
rm -f "$OUTPUT"
echo "Building macOS DMG locally..."
hdiutil create -volname "Rúnmál" -srcfolder "$DMG_ROOT" -ov -format UDZO "$OUTPUT"

HASH="$(shasum -a 256 "$OUTPUT" | awk '{print $1}')"
echo
echo "Rúnmál macOS package built successfully."
echo "File: $OUTPUT"
echo "SHA-256: $HASH"
echo
echo "This build was produced locally on this Mac. No GitHub Actions were used."
