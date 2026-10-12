"""S102 acceptance: local auth boundary."""

import logging
import os
import stat

import pytest
import uvicorn
from fastapi.testclient import TestClient

from runmal import __main__ as cli
from runmal.app import create_app
from runmal.auth import CREDENTIAL_FILENAME, data_dir, get_or_create_credential


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(isolated_data_dir):
    return TestClient(create_app())


def test_healthz_public_200(client) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_401_without_token(client) -> None:
    assert client.get("/api/v1/status").status_code == 401


def test_protected_401_with_wrong_token(client) -> None:
    resp = client.get("/api/v1/status", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_protected_200_with_valid_token(client, isolated_data_dir) -> None:
    token = get_or_create_credential()
    resp = client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["auth"] == "local"


def test_secret_absent_from_error_responses(client, isolated_data_dir) -> None:
    token = get_or_create_credential()
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        body = client.get("/api/v1/status", headers=headers).text
        assert token not in body


def test_secret_absent_from_logs(client, isolated_data_dir, caplog) -> None:
    token = get_or_create_credential()
    with caplog.at_level(logging.DEBUG):
        client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
        client.get("/api/v1/status")
    assert token not in caplog.text


def test_credential_file_is_owner_only(isolated_data_dir) -> None:
    get_or_create_credential()
    mode = stat.S_IMODE(os.stat(data_dir() / CREDENTIAL_FILENAME).st_mode)
    assert mode == 0o600


def test_credential_stable_across_calls(isolated_data_dir) -> None:
    assert get_or_create_credential() == get_or_create_credential()


def test_serve_binds_loopback_by_default(monkeypatch) -> None:
    assert cli.DEFAULT_HOST == "127.0.0.1"
    args = cli.build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1"
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cli.main(["serve", "--port", "18098"]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 18098
