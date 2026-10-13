"""One-button backend installation (ADR-0005 / ADR-0006).

Rúnmál ships a clean default tree. Everything beyond it arrives ONLY
through an explicit per-backend install action taken by the user in
settings — the interoperability principle in code form (Volmarr,
2026-10-13): *ship clean lawful defaults; user additions are user
choice under user responsibility; design for interop with outside
tools of any kind.*

This module is the shared machinery behind that button:

* :class:`InstallPlan` — the declarative recipe for one backend:
  python packages (installed with dependency resolution DISABLED —
  ``pip install --no-deps`` — so a backend can never smuggle an
  unlisted transitive package, e.g. Chatterbox's GPL ``pykakasi``,
  into the tree), an optional pinned git checkout (CosyVoice ships
  from its GitHub repository, never from the name-squatted PyPI
  project), and model downloads.
* :func:`run_install` executes a plan step by step, recording progress
  in a JSON state file the settings UI polls. ``enable=False`` plans
  (registered-but-unverified STT extras) refuse to run: there is no
  code path that installs them until the forge verifies a recipe.
* :func:`backend_status` reports one backend's state for the UI:
  installed or not, its real-tree license audit (verdict displayed as
  information for user-installed backends; the gate binds only the
  default shipped tree), and the honest user-install notice.

Installs land in the active Python environment plus a vendor dir
(``RUNMAL_VENDOR_DIR`` or ``<data dir>/vendor``) for git checkouts and
downloaded model files. Nothing here runs at import time or in the
default install path — only when a user presses the button (or a test
or operator invokes it deliberately).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from runmal.voice.license_audit import AuditReport, audit_snapshot, installed_snapshot

#: Notice shown in the UI for every backend that is not part of the
#: default shipped tree. The wording is a product requirement
#: (VOICE_LICENSE_MATRIX.md scope section), not decoration.
USER_INSTALL_NOTICE = (
    "Not shipped with Rúnmál. Installed by you, at your request — this "
    "backend's own license terms apply to your installation. Rúnmál "
    "shows the license audit of the installed tree as information; "
    "what you install is your choice and your responsibility."
)

#: Label for registry entries the forge has not real-model-verified.
UNVERIFIED_LABEL = "user-installed — not forge-verified"


@dataclass(frozen=True)
class InstallPlan:
    """Declarative install recipe for one registered backend."""

    key: str
    kind: str  # "tts" | "stt"
    #: pip install --no-deps targets (exact pins / VCS URLs).
    pip_packages: tuple[str, ...] = ()
    #: (git URL, pinned commit, checkout dir name under the vendor dir)
    git_checkout: tuple[str, str, str] | None = None
    #: (URL, destination file name under the vendor models dir)
    downloads: tuple[tuple[str, str], ...] = ()
    #: Import name whose presence proves the runtime is installed.
    probe_import: str = ""
    #: False = registered only; the button explains, never installs.
    enable: bool = True
    note: str = ""
    #: Optional "module:function" run as the final install step —
    #: downloads the backend's model through its own runtime and
    #: smoke-tests that the installed tree imports cleanly.
    warmup: str = ""


@dataclass
class InstallState:
    key: str
    status: str = "not_started"  # not_started|running|done|failed|refused
    step: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    def as_dict(self) -> dict:
        return {
            "key": self.key, "status": self.status, "step": self.step,
            "error": self.error, "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def data_dir() -> Path:
    return Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))


def vendor_dir() -> Path:
    override = os.environ.get("RUNMAL_VENDOR_DIR")
    return Path(override) if override else data_dir() / "vendor"


def _state_path() -> Path:
    return data_dir() / "voice_install_state.json"


def _load_states() -> dict[str, InstallState]:
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: InstallState(**{f: v.get(f) for f in
            ("key", "status", "step", "error", "started_at", "finished_at")})
            for k, v in raw.items()}


def _save_state(state: InstallState) -> None:
    states = _load_states()
    states[state.key] = state
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v.as_dict() for k, v in states.items()},
                              indent=2), encoding="utf-8")
    tmp.replace(path)


def install_state(key: str) -> InstallState:
    return _load_states().get(key, InstallState(key=key))


def is_installed(plan: InstallPlan) -> bool:
    """True when the plan's runtime is importable (or, for model-only
    plans, when its downloads are all present)."""
    if plan.probe_import:
        import importlib.util
        return importlib.util.find_spec(plan.probe_import) is not None
    if plan.downloads:
        models = vendor_dir() / "models"
        return all((models / name).exists() for _, name in plan.downloads)
    return install_state(plan.key).status == "done"


def _run(cmd: list[str], *, step: str, state: InstallState,
         runner=None, timeout: int = 3600) -> None:
    state.step = step
    _save_state(state)
    run = runner or subprocess.run
    proc = run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"step '{step}' failed ({cmd[0]}): {tail}")


def run_install(plan: InstallPlan, *, runner=None, timeout: int = 3600) -> InstallState:
    """Execute one plan. Refuses (status ``refused``) when the plan is
    not enabled — registered-but-unverified backends have no install
    path until the forge ships a verified recipe."""
    state = InstallState(key=plan.key, status="running", started_at=time.time())
    _save_state(state)
    try:
        if not plan.enable:
            raise PermissionError(
                f"backend '{plan.key}' is registered but has no verified "
                "install recipe yet — nothing was installed.")
        vdir = vendor_dir()
        vdir.mkdir(parents=True, exist_ok=True)
        if plan.pip_packages:
            _run([sys.executable, "-m", "pip", "install", "--no-deps",
                  *plan.pip_packages],
                 step="pip install --no-deps (curated set)", state=state,
                 runner=runner, timeout=timeout)
        if plan.git_checkout is not None:
            url, commit, dirname = plan.git_checkout
            dest = vdir / dirname
            if not dest.exists():
                _run(["git", "clone", url, str(dest)], step="git clone",
                     state=state, runner=runner, timeout=timeout)
            _run(["git", "-C", str(dest), "checkout", commit],
                 step=f"pin commit {commit[:12]}", state=state,
                 runner=runner, timeout=timeout)
        if plan.downloads:
            models = vdir / "models"
            models.mkdir(parents=True, exist_ok=True)
            for url, name in plan.downloads:
                _run(["curl", "-fL", "-o", str(models / name), url],
                     step=f"download {name}", state=state, runner=runner,
                     timeout=timeout)
        if plan.warmup:
            state.step = "warm-up (model download + import smoke test)"
            _save_state(state)
            module_name, _, func_name = plan.warmup.partition(":")
            import importlib
            func = getattr(importlib.import_module(module_name), func_name)
            func()
        state.status = "done"
        state.step = "installed"
    except Exception as exc:  # surfaced to the UI, never swallowed
        state.status = "refused" if isinstance(exc, PermissionError) else "failed"
        state.error = str(exc)
    state.finished_at = time.time()
    _save_state(state)
    return state


_install_lock = threading.Lock()
_install_threads: dict[str, threading.Thread] = {}


def start_install(plan: InstallPlan) -> InstallState:
    """Start an install in a background thread (the one-button path).

    Idempotent: pressing the button twice never runs two installers.
    """
    with _install_lock:
        current = install_state(plan.key)
        thread = _install_threads.get(plan.key)
        if current.status == "running" and thread is not None and thread.is_alive():
            return current
        thread = threading.Thread(target=run_install, args=(plan,),
                                  name=f"runmal-install-{plan.key}", daemon=True)
        _install_threads[plan.key] = thread
        thread.start()
        return InstallState(key=plan.key, status="running", step="starting")


def audit_for_plan(plan: InstallPlan, *, tree_packages: tuple[str, ...] = ()) -> AuditReport | None:
    """Audit the backend's REAL installed tree; None when not installed.

    With ``tree_packages`` empty the whole current environment is
    audited — the honest view for backends whose tree is the shared
    environment (the default shipped pair). User-installed backends
    pass their curated package list to scope the verdict display.
    """
    if not is_installed(plan):
        return None
    snapshot = installed_snapshot(tree_packages or None)
    return audit_snapshot(snapshot)


def backend_status(plan: InstallPlan, *, default_shipped: bool,
                   verified: bool, tree_packages: tuple[str, ...] = ()) -> dict:
    """UI-facing status for one registered backend."""
    installed = is_installed(plan)
    report = audit_for_plan(plan, tree_packages=tree_packages) if installed else None
    state = install_state(plan.key)
    return {
        "key": plan.key,
        "kind": plan.kind,
        "default_shipped": default_shipped,
        "verified": verified,
        "installed": installed,
        "install_status": state.status,
        "install_step": state.step,
        "install_error": state.error,
        "installable": plan.enable,
        "notice": "" if default_shipped else USER_INSTALL_NOTICE,
        "unverified_label": "" if verified else UNVERIFIED_LABEL,
        "audit": None if report is None else {
            "passed": report.passed,
            "violations": list(report.violations),
            "checked": report.checked,
            "binding": default_shipped,
        },
        "note": plan.note,
    }
