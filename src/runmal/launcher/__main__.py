"""Command entry point for the cross-platform Rúnmál launcher."""

from __future__ import annotations

import argparse
import json
import sys

from runmal.launcher import core


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runmal-launcher",
        description="Rúnmál desktop launcher",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="open",
        choices=("open", "start", "stop", "restart", "status", "control", "doctor", "_serve"),
    )
    parser.add_argument("--port", type=int, default=core.DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start/authenticate without opening the default browser (testing/automation).",
    )
    return parser


def _serve(port: int) -> int:
    import uvicorn

    from runmal.app import create_app, default_session_factory

    uvicorn.run(
        create_app(default_session_factory()),
        host=core.DEFAULT_HOST,
        port=port,
        log_config=None,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "_serve":
            return _serve(args.port)
        if args.command == "open":
            url = core.open_runmal(args.port, browser=not args.no_browser)
            if args.no_browser:
                print(url)
            return 0
        if args.command == "start":
            info = core.start_server(args.port)
            print(json.dumps(info.to_dict(), indent=2))
            return 0
        if args.command == "stop":
            stopped = core.stop_server(args.port)
            print("stopped" if stopped else "no launcher-managed server was running")
            return 0
        if args.command == "restart":
            info = core.restart_server(args.port)
            print(json.dumps(info.to_dict(), indent=2))
            return 0
        if args.command == "status":
            print(json.dumps(core.status(args.port).to_dict(), indent=2))
            return 0
        if args.command == "doctor":
            print(core.diagnostics_text(args.port))
            return 0
        if args.command == "control":
            from runmal.launcher.gui import run_control_center

            run_control_center(args.port)
            return 0
    except core.LauncherError as exc:
        # Packaged GUI builds have no terminal, so make failures visible there.
        if getattr(sys, "frozen", False):
            try:
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Rúnmál", str(exc), parent=root)
                root.destroy()
            except Exception:
                pass
        print(f"Rúnmál launcher: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
