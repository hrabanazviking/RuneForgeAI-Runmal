"""Rúnmál command-line entrypoint."""

from __future__ import annotations

import argparse
import sys

from runmal import __version__

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8098


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runmal",
        description="Rúnmál — sovereign AI chat app",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Run the local API server")
    serve.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind host (default: {DEFAULT_HOST})",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind port (default: {DEFAULT_PORT})",
    )
    backup = sub.add_parser("backup", help="SQLite backup operations (S114)")
    bsub = backup.add_subparsers(dest="backup_command")
    bcreate = bsub.add_parser("create", help="Online-backup the live database")
    bcreate.add_argument(
        "--output",
        default=None,
        help="Destination path (default: data-dir backups/runmal-backup-<ts>.db)",
    )
    bverify = bsub.add_parser("verify", help="Integrity-check a backup file")
    bverify.add_argument("path", help="Backup file to verify")
    bstage = bsub.add_parser(
        "stage",
        help="Restore a backup to a staging path and verify it (live DB untouched)",
    )
    bstage.add_argument("backup", help="Backup file to restore")
    bstage.add_argument(
        "--staging",
        default=None,
        help="Staging destination (default: data-dir staging/restore-<ts>.db)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        import uvicorn

        from runmal.app import create_app, default_session_factory

        uvicorn.run(create_app(default_session_factory()), host=args.host, port=args.port)
    elif args.command == "backup":
        return _run_backup(args)
    return 0


def _run_backup(args: argparse.Namespace) -> int:
    import json

    from runmal.backups import service

    try:
        if args.backup_command == "create":
            info = service.backup_database(dest=args.output)
        elif args.backup_command == "verify":
            info = service.verify_backup(args.path)
        elif args.backup_command == "stage":
            info = service.stage_restore(args.backup, staging_path=args.staging)
        else:
            print("usage: runmal backup {create|verify|stage} ...", file=sys.stderr)
            return 2
    except service.BackupError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(info.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
