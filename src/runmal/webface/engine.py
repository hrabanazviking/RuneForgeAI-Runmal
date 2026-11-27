"""Engine client: the webface's one road to the Rúnmál engine.

Holds the engine base URL plus the engine's local credential, read
server-side from the engine data dir at startup (the credential file
the engine itself owns). The credential is sent as a Bearer header
on engine calls only — it never reaches a browser, a page, or a log
line (INV-023). Engine calls use httpx, an existing project
dependency; the webface's own server is stdlib-only (ADR-0012).
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

CREDENTIAL_FILENAME = "local_credential"


class EngineError(Exception):
    """An engine call failed; carries a plain message + HTTP status."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


def default_engine_data_dir() -> Path:
    override = os.environ.get("RUNMAL_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "runmal"


def read_engine_credential(engine_data_dir: Path) -> str:
    """Read the engine's local credential from its data dir.

    Raises EngineError when the file is missing or empty — the
    webface cannot serve chat without it, and guessing is worse
    than saying so.
    """
    path = Path(engine_data_dir) / CREDENTIAL_FILENAME
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise EngineError(
            f"engine credential not readable at {path}: {exc}") from exc
    if not token:
        raise EngineError(f"engine credential file is empty: {path}")
    return token


class EngineClient:
    def __init__(self, base_url: str, credential: str):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {credential}"},
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=30.0,
                                  pool=30.0),
            trust_env=False,
        )

    # -- plumbing ---------------------------------------------------------

    def _request(self, method: str, path: str,
                 json_body: Any = None) -> Any:
        try:
            response = self._http.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise EngineError(
                f"engine unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or "")
            except ValueError:
                detail = ""
            raise EngineError(
                detail or f"engine answered {response.status_code}",
                status=response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None


    # -- W-02: generic plumbing for characters/library ----------------

    def request(self, method, path, json_body=None, params=None,
                files=None, data=None):
        try:
            response = self._http.request(
                method, path, json=json_body, params=params,
                files=files, data=data)
        except httpx.HTTPError as exc:
            raise EngineError(
                f"engine unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or "")
            except ValueError:
                detail = ""
            raise EngineError(
                detail or f"engine answered {response.status_code}",
                status=response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def request_bytes(self, method, path):
        try:
            response = self._http.request(method, path)
        except httpx.HTTPError as exc:
            raise EngineError(
                f"engine unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise EngineError(f"engine answered {response.status_code}",
                              status=response.status_code)
        return response.content, response.headers.get(
            "content-type", "application/octet-stream")

    # -- reads --------------------------------------------------------------

    def status(self) -> Any:
        return self._request("GET", "/api/v1/status")

    def list_characters(self) -> list:
        payload = self._request("GET", "/api/v1/characters")
        return payload if isinstance(payload, list) else []

    def list_chats(self) -> list:
        payload = self._request("GET", "/api/v1/chats")
        return payload if isinstance(payload, list) else []

    def list_messages(self, chat_id: str) -> list:
        payload = self._request(
            "GET", f"/api/v1/chats/{chat_id}/messages")
        return payload if isinstance(payload, list) else []

    # -- writes -------------------------------------------------------------

    def create_chat(self, *, character_id: str, title: str = "") -> Any:
        body: dict[str, Any] = {"character_id": character_id}
        if title:
            body["title"] = title
        return self._request("POST", "/api/v1/chats", json_body=body)

    def append_message(self, chat_id: str, role: str, content: str) -> Any:
        return self._request(
            "POST", f"/api/v1/chats/{chat_id}/messages",
            json_body={"role": role, "content": content})

    def cancel_generate(self, request_id: str) -> bool:
        payload = self._request(
            "POST", "/api/v1/generate/cancel",
            json_body={"request_id": request_id})
        return bool(isinstance(payload, dict) and payload.get("cancelled"))

    # -- generation -----------------------------------------------------------

    def stream_generate(self, chat_id: str,
                        request_id: str) -> Iterator[tuple[str, dict]]:
        """Stream one composed turn from POST /api/v1/generate.

        Yields (kind, payload) pairs: first ("started", {backend_key,
        mode}) from the response headers, then one pair per SSE event
        with kind = the event's own type (token / reasoning / usage /
        error / done) and the full event dict as payload.
        """
        body = {"chat_id": chat_id, "request_id": request_id}
        try:
            with self._http.stream(
                    "POST", "/api/v1/generate", json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    raise EngineError(
                        f"engine answered {response.status_code} "
                        "for /generate", status=response.status_code)
                yield ("started", {
                    "backend_key": response.headers.get("X-Backend-Key", ""),
                    "mode": response.headers.get("X-Generation-Mode", ""),
                })
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:"):].strip())
                    except ValueError:
                        continue
                    if isinstance(event, dict) and event.get("type"):
                        yield (str(event["type"]), event)
        except httpx.HTTPError as exc:
            raise EngineError(
                f"engine unreachable: {exc.__class__.__name__}") from exc
