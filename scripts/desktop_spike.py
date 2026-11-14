"""Desktop-shell spike (R-01): Qt window + engine in-process, /healthz proof.

The gating proof for the native windowed shell (ADR-0010): a PySide6
QMainWindow is created and shown while the Rúnmál engine runs in the same
process (uvicorn in a worker thread) and answers /healthz.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_spike.py

Prints one line:  R01_RESULT {json}
Exit code 0 only if the window was shown AND /healthz answered
{"status": "ok"}.
"""

import json
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"platform": sys.platform, "python": sys.version.split()[0]}

from PySide6 import __version__ as pyside_version  # noqa: E402
from PySide6.QtCore import qVersion  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow  # noqa: E402

RESULT["pyside6"] = pyside_version
RESULT["qt"] = qVersion()

app = QApplication(sys.argv)
win = QMainWindow()
win.setWindowTitle("Runmal R-01 spike")
win.setCentralWidget(QLabel("Runmal"))
win.resize(640, 480)
win.show()
app.processEvents()
RESULT["window_shown"] = bool(win.isVisible())
RESULT["window_title"] = win.windowTitle()

import uvicorn  # noqa: E402

from runmal.app import create_app, default_session_factory  # noqa: E402

PORT = 18098
config = uvicorn.Config(
    create_app(default_session_factory()),
    host="127.0.0.1",
    port=PORT,
    log_level="error",
)
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()

health = None
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/healthz", timeout=2
        ) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            break
    except Exception:
        time.sleep(0.5)
RESULT["healthz"] = health
server.should_exit = True
thread.join(timeout=10)
win.close()
app.quit()
print("R01_RESULT " + json.dumps(RESULT, sort_keys=True))
sys.exit(0 if (RESULT["window_shown"] and health and health.get("status") == "ok") else 1)
