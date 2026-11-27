"""Run the Rúnmál web face: python -m runmal.webface [flags].

Every setting comes from a CLI flag or an environment variable —
no address is baked in beyond the loopback defaults:
  --host         RUNMAL_WEBFACE_HOST        (default 127.0.0.1)
  --port         RUNMAL_WEBFACE_PORT        (default 8195)
  --engine-url   RUNMAL_WEBFACE_ENGINE_URL  (default http://127.0.0.1:8098)
  --data-dir     RUNMAL_WEBFACE_DATA_DIR    (default ~/.local/share/runmal-webface)
  --engine-data-dir  RUNMAL_DATA_DIR        (default ~/.local/share/runmal)
"""
from __future__ import annotations

import argparse
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from .app import WebfaceApp, make_handler
from .engine import EngineClient, default_engine_data_dir, read_engine_credential
from .store import Store


def _default_data_dir() -> Path:
    override = os.environ.get("RUNMAL_WEBFACE_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "runmal-webface"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runmal-webface", description="Rúnmál web face (W-01)")
    parser.add_argument(
        "--host", default=os.environ.get("RUNMAL_WEBFACE_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("RUNMAL_WEBFACE_PORT", "8195")))
    parser.add_argument(
        "--engine-url",
        default=os.environ.get("RUNMAL_WEBFACE_ENGINE_URL",
                               "http://127.0.0.1:8098"))
    parser.add_argument("--data-dir", default=str(_default_data_dir()))
    parser.add_argument(
        "--engine-data-dir",
        default=os.environ.get("RUNMAL_DATA_DIR") or None,
        help="engine data dir holding local_credential "
             "(default: the engine's own resolution)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    engine_data_dir = (Path(args.engine_data_dir)
                       if args.engine_data_dir else default_engine_data_dir())
    # The engine creates its local credential lazily; obtain it the
    # engine's own way (runmal.auth.get_or_create_credential, the
    # launcher's road) scoped to the engine data dir, then read the
    # file the webface's client will present. Same OS user, same
    # single-owner credential — never logged, never sent to browsers.
    os.environ["RUNMAL_DATA_DIR"] = str(engine_data_dir)
    from runmal.auth import get_or_create_credential
    get_or_create_credential()
    credential = read_engine_credential(engine_data_dir)
    store = Store(Path(args.data_dir))
    engine = EngineClient(args.engine_url, credential)
    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(WebfaceApp(store, engine)))
    server.daemon_threads = True
    print(f"runmal-webface listening on {args.host}:{args.port} "
          f"(engine {args.engine_url})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
