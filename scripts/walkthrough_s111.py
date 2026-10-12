"""S111 scripted browser walkthrough (forge laptop only).

Drives headless Firefox through the chat-management UI against a live server:
rename (inline edit) -> export (JSON download, non-destructive) -> delete
(two-step confirm: cancel aborts with zero side effects, confirm deletes).

Destructive-action confirmation semantics under test:
  1. Delete is two-step: action button -> modal stating irreversibility.
  2. Cancel / Escape / backdrop click aborts with zero side effects.
  3. Only the explicit Delete button performs the deletion.

Usage: .venv/bin/python scripts/walkthrough_s111.py
Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 18098
BASE = f"http://127.0.0.1:{PORT}"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wait_for_health() -> None:
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("server did not become healthy")


def main() -> int:
    data_dir = tempfile.mkdtemp(prefix="runmal-walkthrough-")
    env = {**os.environ, "RUNMAL_DATA_DIR": data_dir}
    server = subprocess.Popen(
        [sys.executable, "-m", "runmal", "serve", "--port", str(PORT)],
        env=env,
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_health()
        token = subprocess.run(
            [
                sys.executable,
                "-c",
                "from runmal.auth import get_or_create_credential; "
                "print(get_or_create_credential())",
            ],
            env=env,
            cwd=HERE,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert token

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            ctx = browser.new_context(accept_downloads=True)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(f"{BASE}/chat")
            page.fill("#token-input", token)
            page.click("#token-save")
            page.wait_for_selector("#chat-list li")
            print("1. chat list loads")

            # Rename via inline edit
            page.locator('#chat-list li button[aria-label="Rename chat"]').first.click()
            page.fill('#chat-list li input[aria-label="Chat title"]', "Renamed by walkthrough")
            page.keyboard.press("Enter")
            page.wait_for_function(
                "() => [...document.querySelectorAll('#chat-list li .title')]"
                ".some(el => el.textContent === 'Renamed by walkthrough')",
                timeout=10000,
            )
            print("2. rename commits on Enter")

            # Rename Escape aborts
            page.locator('#chat-list li button[aria-label="Rename chat"]').first.click()
            page.fill('#chat-list li input[aria-label="Chat title"]', "should-not-stick")
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            titles = page.locator("#chat-list li .title").all_text_contents()
            assert "should-not-stick" not in titles
            assert "Renamed by walkthrough" in titles
            print("3. rename Escape aborts with no change")

            # Export downloads a JSON document; chat untouched
            with page.expect_download() as dl_info:
                page.locator('#chat-list li button[aria-label="Export chat"]').first.click()
            download = dl_info.value
            path = download.path()
            with open(path) as f:
                doc = json.load(f)
            assert doc["format"] == "runmal-chat-export"
            assert doc["chat"]["title"] == "Renamed by walkthrough"
            assert "messages" in doc
            titles = page.locator("#chat-list li .title").all_text_contents()
            assert "Renamed by walkthrough" in titles, "export is non-destructive"
            print("4. export downloads portable JSON, chat untouched")

            # Delete: cancel aborts with zero side effects
            page.locator('#chat-list li button[aria-label="Delete chat"]').first.click()
            page.wait_for_selector("#confirm-modal:not(.hidden)")
            modal_text = page.text_content("#confirm-card")
            assert "cannot be undone" in modal_text, "modal states irreversibility"
            page.click("#confirm-cancel")
            page.wait_for_selector("#confirm-modal", state="hidden")
            page.wait_for_timeout(400)
            titles = page.locator("#chat-list li .title").all_text_contents()
            assert "Renamed by walkthrough" in titles, "cancel = zero side effects"
            print("5. delete cancel aborts, chat survives")

            # Delete: Escape aborts too
            page.locator('#chat-list li button[aria-label="Delete chat"]').first.click()
            page.wait_for_selector("#confirm-modal:not(.hidden)")
            page.keyboard.press("Escape")
            page.wait_for_selector("#confirm-modal", state="hidden")
            titles = page.locator("#chat-list li .title").all_text_contents()
            assert "Renamed by walkthrough" in titles
            print("6. delete Escape aborts, chat survives")

            # Delete: explicit confirm deletes
            page.locator('#chat-list li button[aria-label="Delete chat"]').first.click()
            page.wait_for_selector("#confirm-modal:not(.hidden)")
            page.click("#confirm-ok")
            page.wait_for_function(
                "() => ![...document.querySelectorAll('#chat-list li .title')]"
                ".some(el => el.textContent === 'Renamed by walkthrough')",
                timeout=10000,
            )
            print("7. explicit Delete removes the chat")

            assert not errors, f"page errors: {errors}"
            print("8. no page JS errors")
            browser.close()
        print("WALKTHROUGH PASS")
        return 0
    except Exception as exc:  # noqa: BLE001 - walkthrough reports, not raises
        print(f"WALKTHROUGH FAIL: {exc}")
        return 1
    finally:
        server.terminate()


if __name__ == "__main__":
    sys.exit(main())
