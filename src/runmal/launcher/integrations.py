"""Per-user desktop integrations for the Rúnmál launcher (D004/D005)."""

from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

AUTOSTART_NAME = "runmal"


def launcher_invocation(command: str = "open") -> list[str]:
    """Return a command that invokes this exact installed/frozen launcher."""
    if getattr(sys, "frozen", False):
        return [sys.executable, command]
    return [sys.executable, "-m", "runmal.launcher", command]


def _linux_autostart_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "autostart" / "runmal.desktop"


def _macos_launchagent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "dev.runmal.launcher.plist"


def _windows_run_value() -> tuple[object, str]:
    import winreg

    key = winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
    )
    return key, "Runmal"


def autostart_enabled() -> bool:
    if os.name == "nt":
        try:
            import winreg

            key, name = _windows_run_value()
            try:
                winreg.QueryValueEx(key, name)
                return True
            finally:
                winreg.CloseKey(key)
        except OSError:
            return False
    if sys.platform == "darwin":
        return _macos_launchagent_path().is_file()
    return _linux_autostart_path().is_file()


def set_autostart(enabled: bool) -> None:
    """Enable/disable current-user startup without administrator rights."""
    command = launcher_invocation("start")

    if os.name == "nt":
        import winreg

        key, name = _windows_run_value()
        try:
            if enabled:
                winreg.SetValueEx(
                    key,
                    name,
                    0,
                    winreg.REG_SZ,
                    subprocess.list2cmdline(command),
                )
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return

    if sys.platform == "darwin":
        path = _macos_launchagent_path()
        if not enabled:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": "dev.runmal.launcher",
            "ProgramArguments": command,
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
        }
        with path.open("wb") as handle:
            plistlib.dump(payload, handle)
        return

    path = _linux_autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = shlex.join(command)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Rúnmál\n"
        "Comment=Start the local Rúnmál service at login\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
