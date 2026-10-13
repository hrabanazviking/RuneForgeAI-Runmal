"""``runmal doctor`` — installation diagnostics (S804).

Per BACKUP_AND_RECOVERY §8, the doctor verifies the installation's
vital signs and reports SPECIFIC, ACTIONABLE findings: what is wrong,
where, and what to do about it. It works on a possibly-broken install,
so database checks use read-only raw SQLite rather than the app stack.

Statuses: ``ok`` / ``warn`` (degraded but usable) / ``fail`` (broken).
The doctor never prints secret values — it may report that a secret
reference exists or is missing, never what it contains. Exit-code
semantics live in the CLI: any ``fail`` finding fails the run.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from runmal import __version__
from runmal.auth import data_dir
from runmal.db.migrate import current_revision
from runmal.db.migrations import MIGRATIONS

HEAD_REVISION = MIGRATIONS[-1][0]
DEFAULT_PORT = 8098

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Finding:
    check: str
    status: str  # OK | WARN | FAIL
    detail: str
    action: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DoctorReport:
    app_version: str
    db_path: str
    findings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.status != FAIL for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "app_version": self.app_version,
            "db_path": self.db_path,
            "ok": self.ok,
            "summary": {
                status: sum(1 for f in self.findings if f.status == status)
                for status in (OK, WARN, FAIL)
            },
            "findings": [f.to_dict() for f in self.findings],
        }


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def check_database(db_path: Path) -> list[Finding]:
    if not db_path.is_file():
        return [
            Finding(
                "database",
                FAIL,
                f"no database at {db_path}",
                "start the app once to create it, or restore a backup "
                "(runmal backup stage / archive import)",
            )
        ]
    findings = []
    try:
        conn = _connect_ro(db_path)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            if len(rows) == 1 and rows[0][0] == "ok":
                findings.append(Finding("database_integrity", OK, "integrity_check ok"))
            else:
                findings.append(
                    Finding(
                        "database_integrity",
                        FAIL,
                        f"integrity_check: {rows[0][0] if rows else 'no result'}",
                        "restore the newest verified backup into staging "
                        "and compare (runmal backup full-stage)",
                    )
                )
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                findings.append(
                    Finding(
                        "database_foreign_keys",
                        FAIL,
                        f"{len(fk)} foreign key violations "
                        f"(first: table {fk[0][0]!r} row {fk[0][1]})",
                        "restore from a verified backup; do not keep "
                        "writing to a referentially broken database",
                    )
                )
            else:
                findings.append(Finding("database_foreign_keys", OK, "foreign_key_check clean"))
        finally:
            conn.close()
    except sqlite3.Error as exc:
        findings.append(
            Finding(
                "database_integrity",
                FAIL,
                f"database unreadable: {exc}",
                "check the file is a Rúnmál SQLite database and is not locked by another process",
            )
        )
        return findings
    try:
        revision = current_revision(db_path)
    except sqlite3.Error as exc:
        findings.append(
            Finding(
                "schema_revision",
                FAIL,
                f"schema revision unreadable: {exc}",
                "the database file is damaged; restore from a verified backup",
            )
        )
        return findings
    if revision is None:
        findings.append(
            Finding(
                "schema_revision",
                FAIL,
                "no schema_migrations recorded",
                "the file is not a migrated Rúnmál database; restore a "
                "backup instead of migrating blind",
            )
        )
    elif revision == HEAD_REVISION:
        findings.append(Finding("schema_revision", OK, f"schema at HEAD ({HEAD_REVISION})"))
    elif revision < HEAD_REVISION:
        findings.append(
            Finding(
                "schema_revision",
                WARN,
                f"schema at {revision}, HEAD is {HEAD_REVISION}",
                "start the app (migrations apply on startup) or run the "
                "S803 upgrade path on a copy first",
            )
        )
    else:
        findings.append(
            Finding(
                "schema_revision",
                FAIL,
                f"schema at {revision} is NEWER than this build's HEAD ({HEAD_REVISION})",
                "upgrade Rúnmál; do not let an older build write to a newer schema",
            )
        )
    return findings


def check_sqlite_vec() -> Finding:
    try:
        import sqlite_vec

        conn = sqlite3.connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            version = conn.execute("SELECT vec_version()").fetchone()[0]
        finally:
            conn.close()
        return Finding("sqlite_vec", OK, f"sqlite-vec loadable ({version})")
    except Exception as exc:  # doctor reports, never crashes
        return Finding(
            "sqlite_vec",
            FAIL,
            f"sqlite-vec unavailable: {type(exc).__name__}: {exc}",
            "reinstall the application environment (sqlite-vec is a "
            "core dependency); vector memory search cannot work without it",
        )


def _default_provider_probe(backend: str, base_url: str) -> tuple[bool, str]:
    """HTTP reachability probe for a configured provider surface."""
    import httpx

    url = base_url.rstrip("/")
    path = "/api/tags" if backend == "ollama" else "/models"
    try:
        resp = httpx.get(f"{url}{path}", timeout=2.0)
        return resp.status_code < 500, f"HTTP {resp.status_code} from {url}{path}"
    except Exception as exc:  # report the class, never headers/secrets
        return False, f"unreachable: {type(exc).__name__}"


def check_providers(
    db_path: Path,
    probe: Callable[[str, str], tuple[bool, str]] | None = None,
) -> list[Finding]:
    probe = probe or _default_provider_probe
    if not db_path.is_file():
        return []
    try:
        return _check_providers(db_path, probe)
    except sqlite3.Error:
        return []  # the database check already reports the damage


def _check_providers(
    db_path: Path,
    probe: Callable[[str, str], tuple[bool, str]],
) -> list[Finding]:
    conn = _connect_ro(db_path)
    try:
        rows = []
        try:
            rows = conn.execute(
                "SELECT DISTINCT chat_backend, config_json FROM backend_profiles"
            ).fetchall()
        except sqlite3.Error:
            rows = []
        conn_rows = []
        try:
            conn_rows = conn.execute(
                "SELECT DISTINCT backend, base_url FROM connection_profiles"
            ).fetchall()
        except sqlite3.Error:
            conn_rows = []
    finally:
        conn.close()
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for backend, config_json in rows:
        base_url = "http://127.0.0.1:8000/v1" if backend == "aesir" else ""
        try:
            config = json.loads(config_json or "{}")
            if isinstance(config, dict) and config.get("base_url"):
                base_url = str(config["base_url"])
        except json.JSONDecodeError:
            pass
        if backend == "ollama":
            base_url = base_url or "http://127.0.0.1:11434"
        elif backend == "openrouter":
            base_url = base_url or "https://openrouter.ai/api/v1"
        seen.add((backend, base_url))
    for backend, base_url in conn_rows:
        seen.add((backend, base_url or ""))
    if not seen:
        return [Finding("providers", OK, "no provider profiles configured")]
    for backend, base_url in sorted(seen):
        if backend in ("", "fake"):
            findings.append(
                Finding(
                    f"provider:{backend or 'fake'}", OK, "local fake backend; no provider to reach"
                )
            )
            continue
        ok, detail = probe(backend, base_url)
        findings.append(
            Finding(
                f"provider:{backend}",
                OK if ok else WARN,
                f"{base_url} — {detail}",
                ""
                if ok
                else "start the provider or switch the profile "
                "to a reachable backend; chats on this profile will fail "
                "until then",
            )
        )
    return findings


def _default_audio_probe() -> tuple[int, str]:
    import sounddevice as sd

    devices = sd.query_devices()
    return len(devices), "sounddevice/PortAudio"


def check_audio(
    probe: Callable[[], tuple[int, str]] | None = None,
) -> Finding:
    probe = probe or _default_audio_probe
    try:
        count, label = probe()
    except Exception as exc:
        return Finding(
            "audio_devices",
            WARN,
            f"audio stack unavailable: {type(exc).__name__}",
            "install the voice extras / PortAudio for microphone and "
            "playback; text chat is unaffected",
        )
    if count > 0:
        return Finding("audio_devices", OK, f"{count} audio device(s) via {label}")
    return Finding(
        "audio_devices",
        WARN,
        "no audio devices found",
        "connect a microphone/speaker for voice mode; text chat is unaffected",
    )


def check_provenance(db_path: Path) -> list[Finding]:
    if not db_path.is_file():
        return []
    try:
        return _check_provenance(db_path)
    except sqlite3.Error:
        return [
            Finding(
                "provenance",
                WARN,
                "provenance checks skipped: database unreadable",
                "fix the database findings first",
            )
        ]


def _check_provenance(db_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    conn = _connect_ro(db_path)
    try:

        def has_table(name: str) -> bool:
            return bool(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (name,),
                ).fetchone()
            )

        if has_table("memory_chunks") and has_table("memories"):
            bad_dims = conn.execute(
                "SELECT COUNT(*) FROM memory_chunks WHERE provider != '' AND dims <= 0"
            ).fetchone()[0]
            if bad_dims:
                findings.append(
                    Finding(
                        "provenance_chunk_dims",
                        FAIL,
                        f"{bad_dims} memory chunk(s) declare a provider but non-positive dims",
                        "rebuild derived indexes for the affected "
                        "memories (memory rebuild) or restore from backup",
                    )
                )
            mismatch = conn.execute(
                "SELECT COUNT(*) FROM memory_chunks c JOIN memories m "
                "ON m.id = c.memory_id WHERE c.provider != '' AND "
                "json_extract(m.embedding_json, '$.provider') IS NOT NULL AND "
                "json_extract(m.embedding_json, '$.provider') != c.provider"
            ).fetchone()[0]
            if mismatch:
                findings.append(
                    Finding(
                        "provenance_provider_mismatch",
                        FAIL,
                        f"{mismatch} chunk(s) disagree with their memory's "
                        "recorded embedding provider",
                        "the embedding space bookkeeping is inconsistent "
                        "(INV-019); rebuild memory indexes under one "
                        "profile, or restore from a verified backup",
                    )
                )
            dangling = conn.execute(
                "SELECT COUNT(*) FROM memory_sources s LEFT JOIN chats c "
                "ON c.id = s.chat_id WHERE s.chat_id IS NOT NULL "
                "AND c.id IS NULL"
            ).fetchone()[0]
            if dangling:
                findings.append(
                    Finding(
                        "provenance_dangling_sources",
                        WARN,
                        f"{dangling} memory source(s) reference a chat that no longer exists",
                        "provenance is partially unrecoverable for those "
                        "memories; the statements remain, their evidence "
                        "link is gone",
                    )
                )
            if not findings:
                findings.append(Finding("provenance", OK, "memory provenance is consistent"))
    finally:
        conn.close()
    return findings


def check_assets(db_path: Path, base: Path) -> list[Finding]:
    if not db_path.is_file():
        return []
    findings: list[Finding] = []
    conn = _connect_ro(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT id, avatar_asset FROM characters "
                "WHERE avatar_asset IS NOT NULL AND avatar_asset != ''"
            ).fetchall()
        except sqlite3.Error:
            rows = []
    finally:
        conn.close()
    missing = []
    known_ids = set()
    for character_id, avatar in rows:
        known_ids.add(character_id)
        if not (base / "assets" / "characters" / character_id / avatar).is_file():
            missing.append(f"{character_id}/{avatar}")
    if missing:
        findings.append(
            Finding(
                "assets_missing",
                WARN,
                f"{len(missing)} character avatar file(s) missing (first: {missing[0]})",
                "restore assets from a full backup "
                "(runmal backup full-stage) or re-import the character",
            )
        )
    assets_root = base / "assets" / "characters"
    if assets_root.is_dir():
        orphans = [d.name for d in assets_root.iterdir() if d.is_dir() and d.name not in known_ids]
        if orphans:
            findings.append(
                Finding(
                    "assets_orphaned",
                    WARN,
                    f"{len(orphans)} asset directorie(s) belong to no "
                    f"character (first: {orphans[0]})",
                    "harmless but taking space; delete after confirming "
                    "the characters are gone for good",
                )
            )
    if not findings:
        findings.append(Finding("assets", OK, "character assets are consistent"))
    return findings


def check_port(port: int = DEFAULT_PORT) -> Finding:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return Finding("port", OK, f"127.0.0.1:{port} is free for the app server")
    except OSError:
        return Finding(
            "port",
            WARN,
            f"127.0.0.1:{port} is already in use",
            "the app may already be running; if not, find the listener "
            f"(e.g. `ss -ltnp | grep {port}`) or serve on another port",
        )
    finally:
        sock.close()


def check_configuration(base: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe_file = base / ".doctor-write-probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        findings.append(Finding("data_dir", OK, f"data dir writable: {base}"))
    except OSError as exc:
        findings.append(
            Finding(
                "data_dir",
                FAIL,
                f"data dir not writable: {base} ({exc})",
                "fix permissions on the data dir or set RUNMAL_DATA_DIR to a writable location",
            )
        )
    from runmal.auth import CREDENTIAL_FILENAME

    if (base / CREDENTIAL_FILENAME).is_file():
        findings.append(Finding("local_credential", OK, "local credential file present"))
    else:
        findings.append(
            Finding(
                "local_credential",
                WARN,
                "no local credential file yet",
                "it is generated on first app start; nothing to do "
                "unless the API rejects every request",
            )
        )
    return findings


def run_doctor(
    *,
    db_path: str | Path | None = None,
    base_dir: Path | None = None,
    port: int = DEFAULT_PORT,
    provider_probe: Callable[[str, str], tuple[bool, str]] | None = None,
    audio_probe: Callable[[], tuple[int, str]] | None = None,
) -> DoctorReport:
    base = base_dir or data_dir()
    db = Path(db_path) if db_path else base / "runmal.db"
    findings: list[Finding] = []
    findings.extend(check_configuration(base))
    findings.extend(check_database(db))
    findings.append(check_sqlite_vec())
    findings.extend(check_providers(db, provider_probe))
    findings.append(check_audio(audio_probe))
    findings.extend(check_provenance(db))
    findings.extend(check_assets(db, base))
    findings.append(check_port(port))
    return DoctorReport(app_version=__version__, db_path=str(db), findings=findings)
