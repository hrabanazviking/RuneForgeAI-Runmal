"""S109 scripted browser walkthrough (forge laptop only).

Drives headless Firefox through the real chat UI against a live server:
token gate -> new chat -> send -> incremental token rendering -> Stop button
wiring (cancel POST with the right request_id) -> persistence across reload.

Usage: .venv/bin/python scripts/walkthrough_s109.py
Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 18099
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
        minted = subprocess.run(
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
        )
        token = minted.stdout.strip()
        assert token, "credential minting failed"

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(f"{BASE}/chat")
            assert "R\u00fanm\u00e1l" in page.title(), page.title()
            print("1. page loads with title")

            # Token gate -> paste credential
            page.wait_for_selector("#token-gate:not(.hidden)")
            page.fill("#token-input", token)
            page.click("#token-save")
            page.wait_for_selector("#token-gate", state="hidden")
            page.wait_for_selector("#chat-list")
            print("2. token gate accepts credential")

            # boot() auto-creates the first chat when empty; use it
            page.wait_for_selector("#chat-list li")
            page.fill("#input", "Hail from the walkthrough")
            page.click("#send")
            page.wait_for_selector(".msg.assistant")
            page.wait_for_function(
                "() => [...document.querySelectorAll('.msg.assistant')].pop()"
                ".textContent === 'R\u00fanm\u00e1l hears you. This is a stub.'",
                timeout=20000,
            )
            page.wait_for_selector("#send:not([disabled])", timeout=20000)
            texts = page.locator(".msg").all_text_contents()
            assert any("Hail from the walkthrough" in t for t in texts)
            print("3. send -> incremental tokens -> full stub reply, history shows both")

            # Reload: history persisted via the API
            page.reload()
            page.wait_for_selector(".msg.assistant")
            texts = page.locator(".msg").all_text_contents()
            assert any("Hail from the walkthrough" in t for t in texts)
            assert any("R\u00fanm\u00e1l hears you" in t for t in texts)
            print("4. reload shows persisted history")

            # Stop wiring, deterministically: hold the SSE stream open from the page
            page.evaluate(
                """() => {
                window.__held = null;
                window.__genRequestId = null;
                const realFetch = window.fetch.bind(window);
                window.fetch = async (url, opts) => {
                  if (typeof url === 'string' && url.endsWith('/api/v1/generate')) {
                    window.__genRequestId = JSON.parse(opts.body).request_id;
                    const stream = new ReadableStream({
                      start(controller) {
                        window.__held = controller;
                        controller.enqueue(new TextEncoder().encode(
                          'data: {"type": "token", "text": "slow "}\\n\\n'));
                      }
                    });
                    return new Response(stream,
                      { headers: { 'content-type': 'text/event-stream' } });
                  }
                  return realFetch(url, opts);
                };
              }"""
            )
            cancelled: list[dict] = []
            page.on(
                "request",
                lambda req: (
                    cancelled.append(req.post_data_json)
                    if req.url.endswith("/api/v1/generate/cancel") and req.method == "POST"
                    else None
                ),
            )
            page.fill("#input", "held generation")
            page.click("#send")
            page.wait_for_selector("#stop:not(.hidden)", timeout=5000)
            bubble_text = page.locator(".msg.assistant").last.text_content()
            assert "slow " in bubble_text, "incremental token rendered before Stop"
            page.click("#stop")
            page.wait_for_function("() => window.__genRequestId !== null", timeout=5000)
            # give the cancel POST a moment to fire
            page.wait_for_timeout(800)
            assert cancelled, "Stop must POST /api/v1/generate/cancel"
            gen_id = page.evaluate("() => window.__genRequestId")
            assert cancelled[0]["request_id"] == gen_id, (cancelled, gen_id)
            print("5. Stop POSTs /generate/cancel with the live request_id")

            # Server's done/cancelled -> UI shows the stopped suffix
            page.evaluate(
                """() => {
                const c = window.__held;
                c.enqueue(new TextEncoder().encode(
                  'data: {"type": "done", "finish_reason": "cancelled"}\\n\\n'));
                c.close();
              }"""
            )
            page.wait_for_selector("#stop", state="hidden", timeout=5000)
            final = page.locator(".msg.assistant").last.text_content()
            assert "stopped" in final, final
            print("6. cancelled stream renders the stopped state")

            assert not errors, f"page errors: {errors}"
            print("7. no page JS errors")
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
