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
    bfull = bsub.add_parser(
        "full-create", help="Create a full backup bundle (database + assets, S802)"
    )
    bfull.add_argument(
        "--output",
        default=None,
        help="Destination bundle path (default: data-dir backups/runmal-full-backup-<ts>.zip)",
    )
    bstagefull = bsub.add_parser(
        "full-stage", help="Validate + stage a full backup bundle with a report"
    )
    bstagefull.add_argument("bundle", help="Full backup bundle (.zip)")
    bstagefull.add_argument(
        "--staging",
        default=None,
        help="Staging directory (default: data-dir staging/full-restore-<ts>)",
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
    archive = sub.add_parser("archive", help="Portable .runmal archive operations (S801)")
    asub = archive.add_subparsers(dest="archive_command")
    aexp = asub.add_parser("export", help="Export a portable .runmal archive")
    aexp.add_argument("--output", required=True, help="Destination .runmal path")
    aexp.add_argument(
        "--user-id",
        default=None,
        help="Owner user id (default: the sole local user, if exactly one)",
    )
    aval = asub.add_parser("validate", help="Validate a .runmal archive")
    aval.add_argument("path", help="Archive file to validate")
    aimp = asub.add_parser(
        "import", help="Import a .runmal archive into a fresh staging directory (S802)"
    )
    aimp.add_argument("path", help="Archive file to import")
    aimp.add_argument(
        "--staging-dir",
        default=None,
        help="Staging directory (default: data-dir staging/archive-import-<ts>)",
    )
    doctor = sub.add_parser("doctor", help="Diagnose the installation (S804)")
    doctor.add_argument("--json", action="store_true", help="Print the report as JSON")
    doctor.add_argument(
        "--port",
        type=int,
        default=8098,
        help="App server port to probe (default: 8098)",
    )
    release = sub.add_parser("release", help="Release artifacts + gates (S806)")
    rsub = release.add_subparsers(dest="release_command")
    rsbom = rsub.add_parser("sbom", help="Print/write the SBOM (CycloneDX JSON)")
    rsbom.add_argument("--out", default=None, help="Write to this file")
    rlic = rsub.add_parser("licenses", help="Print/write the license manifest")
    rlic.add_argument("--out", default=None, help="Write to this file")
    rsub.add_parser("gate", help="Run the license gate over the installed tree")
    rsub.add_parser("check", help="Dry-run release consistency check (S807)")
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
    elif args.command == "archive":
        return _run_archive(args)
    elif args.command == "doctor":
        return _run_doctor(args)
    elif args.command == "release":
        return _run_release(args)
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
        elif args.backup_command == "full-create":
            from runmal.backups import full

            full_info = full.create_full_backup(dest=args.output)
            print(json.dumps(full_info.to_dict(), indent=2))
            return 0
        elif args.backup_command == "full-stage":
            from runmal.backups import full

            report = full.stage_full_restore(args.bundle, staging_root=args.staging)
            print(json.dumps(report.to_dict(), indent=2))
            return 0
        else:
            print(
                "usage: runmal backup {create|verify|stage|full-create|full-stage} ...",
                file=sys.stderr,
            )
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


def _run_archive(args: argparse.Namespace) -> int:
    import asyncio
    import json

    from runmal.portable.archive import ArchiveError

    if args.archive_command == "validate":
        from runmal.portable.archive import validate_archive

        try:
            manifest = validate_archive(args.path)
        except ArchiveError as exc:
            print(f"archive invalid: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"valid": True, "manifest": manifest}, indent=2))
        return 0
    if args.archive_command == "import":
        import asyncio as _asyncio

        from runmal.portable.restore import import_archive

        async def _import() -> dict:
            if args.staging_dir:
                root = args.staging_dir
            else:
                from datetime import UTC, datetime

                from runmal.auth import data_dir

                root = str(
                    data_dir()
                    / "staging"
                    / f"archive-import-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
                )
            report = await import_archive(args.path, root)
            return report.to_dict()

        try:
            out = _asyncio.run(_import())
        except ArchiveError as exc:
            print(f"archive import failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2))
        return 0
    if args.archive_command != "export":
        print("usage: runmal archive {export|validate} ...", file=sys.stderr)
        return 2

    async def _go() -> dict:
        from sqlalchemy import select

        from runmal.app import default_session_factory
        from runmal.db.models import User
        from runmal.portable.archive import export_archive

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
            info = await export_archive(session, user_id, args.output)
            return info.to_dict()

    try:
        out = asyncio.run(_go())
    except ValueError as exc:
        print(f"archive export failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


def _run_release(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from runmal.release.sbom import (
        build_license_manifest,
        build_sbom,
        gate_report,
    )

    if args.release_command == "gate":
        report = gate_report()
        print(report.summary())
        return 0 if report.passed else 1
    if args.release_command == "check":
        from runmal.release.versioning import check_release_consistency

        result = check_release_consistency()
        print(result.summary())
        return 0 if result.ok else 1
    if args.release_command == "sbom":
        payload = build_sbom()
    elif args.release_command == "licenses":
        payload = build_license_manifest()
    else:
        print("usage: runmal release {sbom|licenses|gate}", file=sys.stderr)
        return 2
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def _run_doctor(args: argparse.Namespace) -> int:
    import json

    from runmal.diagnostics.doctor import FAIL, OK, WARN, run_doctor

    report = run_doctor(port=args.port)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"runmal doctor — app {report.app_version}, db {report.db_path}")
        icons = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}
        for finding in report.findings:
            print(f"[{icons[finding.status]}] {finding.check}: {finding.detail}")
            if finding.action and finding.status != OK:
                print(f"       -> {finding.action}")
        print("overall:", "OK" if report.ok else "PROBLEMS FOUND")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
