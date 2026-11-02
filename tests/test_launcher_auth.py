"""D002 acceptance: one-use launcher bootstrap and browser sessions."""

from fastapi import Depends
from fastapi.testclient import TestClient

from runmal.app import create_app, require_local_auth
from runmal.auth import (
    BOOTSTRAP_FILENAME,
    SESSION_COOKIE_NAME,
    consume_bootstrap_nonce,
    create_bootstrap_nonce,
    create_browser_session,
    data_dir,
    get_or_create_credential,
    verify_browser_session,
)


def test_bootstrap_nonce_is_one_use(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    nonce = create_bootstrap_nonce(now=100)
    assert consume_bootstrap_nonce(nonce, now=101) is True
    assert consume_bootstrap_nonce(nonce, now=102) is False
    assert not (data_dir() / BOOTSTRAP_FILENAME).exists()


def test_wrong_nonce_does_not_destroy_valid_nonce(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    nonce = create_bootstrap_nonce(now=100)
    assert consume_bootstrap_nonce("definitely-wrong", now=101) is False
    assert consume_bootstrap_nonce(nonce, now=102) is True


def test_bootstrap_nonce_expires(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    nonce = create_bootstrap_nonce(now=100)
    assert consume_bootstrap_nonce(nonce, now=1000) is False


def test_browser_session_is_signed_and_expires(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    session = create_browser_session(now=100)
    assert verify_browser_session(session, now=101) is True
    assert verify_browser_session(session + "tampered", now=101) is False
    assert verify_browser_session(session, now=10_000_000) is False


def test_launcher_bootstrap_sets_httponly_session_not_bearer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())
    permanent = get_or_create_credential()
    nonce = create_bootstrap_nonce()

    response = client.get(
        f"/launcher/bootstrap?nonce={nonce}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"
    cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert permanent not in response.text
    assert permanent not in str(response.headers)
    assert nonce not in str(response.headers)

    # The TestClient retains the cookie, so bearerless browser API calls work.
    status = client.get("/api/v1/status")
    assert status.status_code == 200
    assert status.json()["auth"] == "local"


def test_cookie_authenticated_write_requires_same_origin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    app = create_app()

    @app.post("/test-browser-write", dependencies=[Depends(require_local_auth)])
    def browser_write() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    nonce = create_bootstrap_nonce()
    assert client.get(
        f"/launcher/bootstrap?nonce={nonce}",
        follow_redirects=False,
    ).status_code == 303

    assert client.post("/test-browser-write").status_code == 403
    assert client.post(
        "/test-browser-write",
        headers={"Origin": "https://evil.example"},
    ).status_code == 403
    assert client.post(
        "/test-browser-write",
        headers={"Origin": "http://testserver"},
    ).status_code == 200


def test_bearer_write_does_not_require_browser_origin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    app = create_app()

    @app.post("/test-bearer-write", dependencies=[Depends(require_local_auth)])
    def bearer_write() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    token = get_or_create_credential()
    response = client.post(
        "/test-bearer-write",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
