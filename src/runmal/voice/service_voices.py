"""Registered voices on the configured speech service (Amendment 1).

The on-demand CosyVoice waiter exposes a small voice registry
beside its OpenAI-shaped speech surface: ``GET /voices`` lists the
registered zero-shot voices and ``POST /voices`` registers a new
one from {name, transcript, audio_b64}. This module is the
engine's one client for that registry.

Configuration is the speech adapter's own: the base URL comes from
``RUNMAL_SPEECH_BASE_URL`` (see openai_compat.py) - the registry
lives at the service root, i.e. the base URL with its trailing
``/v1`` removed. No address is hardcoded here (house law 7): with
no base URL configured there is no service, and every call says
so plainly instead of guessing a destination.
"""
from __future__ import annotations

import os

import httpx

from runmal.voice.openai_compat import ENV_BASE_URL


class SpeechServiceError(RuntimeError):
    """The configured speech service could not honour a registry call."""


def speech_base_url() -> str:
    return str(os.environ.get(ENV_BASE_URL) or "").rstrip("/")


def service_root_url() -> str:
    """Service root for the registry roads (base URL minus /v1)."""
    base = speech_base_url()
    if not base:
        raise SpeechServiceError(
            "no speech service is configured: RUNMAL_SPEECH_BASE_URL is unset, "
            "so there is no voice registry to reach")
    if base.endswith("/v1"):
        return base[: -len("/v1")]
    return base


def _client() -> httpx.Client:
    return httpx.Client(base_url=service_root_url(), timeout=120.0, trust_env=False)


def list_service_voices() -> list[dict]:
    try:
        with _client() as client:
            resp = client.get("/voices")
    except SpeechServiceError:
        raise
    except httpx.HTTPError as exc:
        raise SpeechServiceError(
            f"speech service unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise SpeechServiceError(f"speech service answered {resp.status_code} for GET /voices")
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def register_service_voice(name: str, transcript: str, audio_b64: str) -> dict:
    name = str(name or "").strip()
    transcript = str(transcript or "").strip()
    audio_b64 = str(audio_b64 or "").strip()
    if not name:
        raise SpeechServiceError("a voice needs a name")
    if not transcript:
        raise SpeechServiceError("a voice needs the exact transcript of its reference audio")
    if not audio_b64:
        raise SpeechServiceError("a voice needs reference audio (base64)")
    try:
        with _client() as client:
            resp = client.post("/voices", json={
                "name": name, "transcript": transcript, "audio_b64": audio_b64})
    except SpeechServiceError:
        raise
    except httpx.HTTPError as exc:
        raise SpeechServiceError(
            f"speech service unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                err = body.get("error")
                detail = str(err.get("message") if isinstance(err, dict) else err or body.get("detail") or "")
        except ValueError:
            detail = ""
        raise SpeechServiceError(detail or f"speech service answered {resp.status_code} for POST /voices")
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}
