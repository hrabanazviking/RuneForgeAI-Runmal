"""PyInstaller/Nuitka-friendly frozen launcher entry."""

from __future__ import annotations

from runmal.launcher.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
