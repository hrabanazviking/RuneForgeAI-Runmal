#!/usr/bin/env bash
# Rúnmál web face — on-demand start/stop/status (W-01, ADR-0012).
#
# Starts the engine (only if it is not already answering /healthz)
# and the webface as detached, stoppable processes with pidfiles +
# logs under the webface data dir. NO systemd, NO enable, NO timer,
# NO watchdog — permanence would need Volmarr's explicit word.
#
# Every address/port/dir comes from the environment or flags:
#   RUNMAL_WEBFACE_HOST / _PORT / _ENGINE_URL / _DATA_DIR
#   RUNMAL_ENGINE_HOST / _PORT, RUNMAL_DATA_DIR, RUNMAL_PYTHON
# Usage: webface_on_demand.sh start|stop|status
set -u

WEBFACE_DATA_DIR="${RUNMAL_WEBFACE_DATA_DIR:-$HOME/.local/share/runmal-webface}"
ENGINE_DATA_DIR="${RUNMAL_DATA_DIR:-$HOME/.local/share/runmal}"
ENGINE_HOST="${RUNMAL_ENGINE_HOST:-127.0.0.1}"
ENGINE_PORT="${RUNMAL_ENGINE_PORT:-8098}"
WEBFACE_HOST="${RUNMAL_WEBFACE_HOST:-127.0.0.1}"
WEBFACE_PORT="${RUNMAL_WEBFACE_PORT:-8195}"
ENGINE_URL="${RUNMAL_WEBFACE_ENGINE_URL:-http://${ENGINE_HOST}:${ENGINE_PORT}}"
PYTHON="${RUNMAL_PYTHON:-python3}"
mkdir -p "$WEBFACE_DATA_DIR"
ENGINE_PIDFILE="$WEBFACE_DATA_DIR/engine.pid"
WEBFACE_PIDFILE="$WEBFACE_DATA_DIR/webface.pid"

_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
_engine_up() { curl -s -m 3 "http://${ENGINE_HOST}:${ENGINE_PORT}/healthz" >/dev/null 2>&1; }

start() {
  if _engine_up; then
    echo "engine already answering on ${ENGINE_HOST}:${ENGINE_PORT} — using it"
  elif _alive "$ENGINE_PIDFILE"; then
    echo "engine process alive but not answering yet (pid $(cat "$ENGINE_PIDFILE"))"
  else
    RUNMAL_DATA_DIR="$ENGINE_DATA_DIR" nohup "$PYTHON" -m runmal serve \
      --host "$ENGINE_HOST" --port "$ENGINE_PORT" \
      > "$WEBFACE_DATA_DIR/engine.log" 2>&1 &
    echo $! > "$ENGINE_PIDFILE"
    echo "engine started (pid $(cat "$ENGINE_PIDFILE"), log $WEBFACE_DATA_DIR/engine.log)"
    for _ in $(seq 1 30); do _engine_up && break; sleep 1; done
    _engine_up || { echo "engine did not answer /healthz in 30s — see engine.log"; return 1; }
  fi
  if _alive "$WEBFACE_PIDFILE"; then
    echo "webface already running (pid $(cat "$WEBFACE_PIDFILE"))"
  else
    RUNMAL_DATA_DIR="$ENGINE_DATA_DIR" nohup "$PYTHON" -m runmal.webface \
      --host "$WEBFACE_HOST" --port "$WEBFACE_PORT" \
      --engine-url "$ENGINE_URL" --data-dir "$WEBFACE_DATA_DIR" \
      --engine-data-dir "$ENGINE_DATA_DIR" \
      > "$WEBFACE_DATA_DIR/webface.log" 2>&1 &
    echo $! > "$WEBFACE_PIDFILE"
    echo "webface started (pid $(cat "$WEBFACE_PIDFILE")) at http://${WEBFACE_HOST}:${WEBFACE_PORT}/"
  fi
}

stop() {
  for f in "$WEBFACE_PIDFILE" "$ENGINE_PIDFILE"; do
    if _alive "$f"; then
      kill "$(cat "$f")" 2>/dev/null && echo "stopped pid $(cat "$f") ($f)"
    fi
    rm -f "$f"
  done
  echo "note: an engine that was already running before 'start' is left alone by design; stop it by its own pid if wanted."
}

status() {
  _engine_up && echo "engine: answering on ${ENGINE_HOST}:${ENGINE_PORT}" || echo "engine: not answering"
  if _alive "$WEBFACE_PIDFILE"; then
    echo "webface: running (pid $(cat "$WEBFACE_PIDFILE")) at http://${WEBFACE_HOST}:${WEBFACE_PORT}/"
  else
    echo "webface: not running"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
