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
    profiles = sub.add_parser("profiles", help="Backend profile operations")
    psub = profiles.add_subparsers(dest="profiles_command")
    pmig = psub.add_parser(
        "migrate-to-aesir",
        help="Migrate an Ollama/OpenRouter profile to Aesir (S704)",
    )
    pmig.add_argument("--profile-id", required=True, help="Source profile id")
    pmig.add_argument(
        "--user-id",
        default=None,
        help="Owner user id (default: the sole local user, if exactly one)",
    )
    pmig.add_argument("--name", default=None, help="Target profile name")
    pmig.add_argument(
        "--chat-model",
        default=None,
        help="Aesir chat model (required for OpenRouter sources)",
    )
    pmig.add_argument(
        "--embeddings",
        action="store_true",
        help="Also migrate embeddings to Aesir (requires --embedding-model)",
    )
    pmig.add_argument("--embedding-model", default=None, help="Aesir embedding model")
    pmig.add_argument("--base-url", default=None, help="Aesir server base URL for the new profile")
    pmig.add_argument(
        "--repoint-chats",
        action="store_true",
        help="Repoint chats from the source profile to the migrated one",
    )
    pmig.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without creating anything",
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
    elif args.command == "profiles":
        return _run_profiles(args)
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


def _run_profiles(args: argparse.Namespace) -> int:
    import asyncio
    import json

    if args.profiles_command != "migrate-to-aesir":
        print("usage: runmal profiles migrate-to-aesir ...", file=sys.stderr)
        return 2

    async def _go() -> dict:
        from sqlalchemy import select

        from runmal.app import default_session_factory
        from runmal.backends import profile_migration
        from runmal.backends.profiles import get_profile, profile_to_dict
        from runmal.db.models import User

        factory = default_session_factory()
        async with factory() as session:
            user_id = args.user_id
            if user_id is None:
                users = list(await session.scalars(select(User)))
                if len(users) != 1:
                    raise ValueError(
                        "--user-id is required unless exactly one local "
                        f"user exists (found {len(users)})"
                    )
                user_id = users[0].id
            source = await get_profile(session, user_id, args.profile_id)
            if source is None:
                raise ValueError(f"profile not found: {args.profile_id}")
            plan_kwargs = {
                "target_name": args.name,
                "aesir_chat_model": args.chat_model,
                "migrate_embeddings": args.embeddings,
                "aesir_embedding_model": args.embedding_model,
                "base_url": args.base_url,
            }
            if args.dry_run:
                plan = profile_migration.plan_profile_migration(source, **plan_kwargs)
                return {"dry_run": True, "plan": plan.to_dict()}
            result = await profile_migration.apply_profile_migration(
                session,
                user_id,
                args.profile_id,
                repoint_chats=args.repoint_chats,
                **plan_kwargs,
            )
            return {
                "dry_run": False,
                "profile": profile_to_dict(result.profile),
                "plan": result.plan.to_dict(),
                "repointed_chats": result.repointed_chats,
            }

    try:
        out = asyncio.run(_go())
    except ValueError as exc:
        print(f"profile migration failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
