"""F-01 acceptance: the generic OpenAI-compatible adapter.

Part I follow-on F-01 (homed by the P-014 gate from P-008's first
recommendation): one adapter covering the ledger's 14 WANTED-GENERIC
rows — chat plus embeddings — passing the shared backend contract
suite, with the connection layer's already-promised ``openai`` kind
(S211) made real behind it. Fixture transports only; no live
endpoint is involved.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.embeddings import (
    OpenAICompatibleEmbeddingBackend,
    check_embedding_contract,
)
from runmal.backends.errors import (
    AuthenticationFailed,
    InvalidRequest,
    ProviderError,
    RateLimited,
)
from runmal.backends.events import Done, TextDelta, UsageUpdate
from runmal.backends.messages import ChatMessage
from runmal.backends.openai_compat import (
    SAMPLERS,
    UNSUPPORTED_SAMPLERS,
    WIRE_NAMES,
    OpenAICompatibleChatBackend,
)
from runmal.backends.params import SamplingParams
from runmal.backends.profiles import (
    build_chat_backend,
    build_embedding_backend,
    create_profile,
    profile_to_dict,
    put_secret,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.generation.compat import OPENAI_PROFILE

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]


def fixture_transport(chat: bytes | None = None, status: int = 200):
    sse = chat if chat is not None else (FIX / "openai_chat.sse").read_bytes()
    models = (FIX / "openai_models.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                status, content=sse, headers={"Content-Type": "text/event-stream"}
            )
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=models, headers={"Content-Type": "application/json"})
        if request.url.path.endswith("/embeddings"):
            payload = json.loads(request.content)
            vectors = [[0.1, 0.2], [0.3, 0.4]][: len(payload["input"])]
            body = {
                "data": [
                    {"index": i, "embedding": v} for i, v in enumerate(vectors)
                ]
            }
            return httpx.Response(200, content=json.dumps(body).encode())
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def backend(**kw) -> OpenAICompatibleChatBackend:
    return OpenAICompatibleChatBackend(
        api_key=contract.CANARY, transport=fixture_transport(**kw)
    )


async def test_fixture_backend_passes_contract():
    await contract.run_all(backend())


async def test_sse_stream_usage_and_done():
    events = [e async for e in backend().chat_stream(MSGS, SamplingParams(), asyncio.Event())]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == (
        "Hello from a generic endpoint"
    )
    usages = [e for e in events if isinstance(e, UsageUpdate)]
    assert usages and usages[0].total_tokens == 14
    assert isinstance(events[-1], Done) and events[-1].reason == "stop"
    types = {e.to_dict()["type"] for e in events}
    assert types <= {"text_delta", "usage", "done"}


async def test_model_metadata_normalized():
    b = backend()
    models = await b.list_models()
    assert [m.model_id for m in models] == ["llama-3.1-8b-instruct", "mistral-large"]
    assert models[0].display_name == "Llama 3.1 8B Instruct (local server)"
    # context_window / max_completion_tokens spellings are honoured too.
    assert models[1].capabilities.context_length == 32768
    assert models[1].capabilities.max_output_tokens == 8192
    assert all(m.backend_key == "openai" for m in models)
    health = await b.health_check()
    assert health.ok and "openai-compatible" in health.detail


async def test_sampler_truth_matches_s208_openai_profile():
    # The declared sampler set IS the S208 openai wire profile's set,
    # and declared + unsupported account for every canonical control.
    assert SAMPLERS == frozenset(OPENAI_PROFILE.wire_names)
    assert WIRE_NAMES == {k: k for k in SAMPLERS}
    # P-052: the canonical vocabulary is the sampler catalogue as
    # data; this test previously hardcoded the pre-P-052 set.
    from runmal.backends.samplers import SAMPLER_NAMES

    canonical = set(SamplingParams().to_bag()) | set(SAMPLER_NAMES)
    assert SAMPLERS | UNSUPPORTED_SAMPLERS == canonical
    assert not (SAMPLERS & UNSUPPORTED_SAMPLERS)


async def test_wire_payload_filters_and_carries_no_stream_options():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, content=(FIX / "openai_chat.sse").read_bytes())

    b = OpenAICompatibleChatBackend(
        api_key="k", model="some-model", transport=httpx.MockTransport(handler)
    )
    params = SamplingParams(
        temperature=0.3, max_output_tokens=16, frequency_penalty=0.2,
        top_k=5, min_p=0.1, repetition_penalty=1.1,
    )
    _ = [e async for e in b.chat_stream(MSGS, params, asyncio.Event())]
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 16
    assert captured["frequency_penalty"] == 0.2
    for dropped in ("top_k", "min_p", "repetition_penalty", "repeat_penalty"):
        assert dropped not in captured
    # P-009's lesson, applied generically: no stream_options is sent.
    assert "stream_options" not in captured
    assert "usage" not in captured
    assert captured["model"] == "some-model"
    assert captured["auth"] == "Bearer k"


async def test_error_payload_and_http_errors_map():
    err_sse = (FIX / "openai_error.sse").read_bytes()
    with pytest.raises(RateLimited):
        _ = [e async for e in backend(chat=err_sse).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]
    with pytest.raises(AuthenticationFailed):
        _ = [e async for e in backend(status=401).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]
    with pytest.raises(InvalidRequest):
        _ = [e async for e in backend(status=422).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_incomplete_stream_raises_instead_of_faking_done():
    truncated = (
        b'data: {"choices": [{"delta": {"content": "partial"},'
        b' "finish_reason": null}]}\n\n'
    )
    with pytest.raises(ProviderError):
        _ = [e async for e in backend(chat=truncated).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_embeddings_pass_contract_and_carry_provenance():
    emb = OpenAICompatibleEmbeddingBackend(
        api_key=contract.CANARY, transport=fixture_transport()
    )
    await check_embedding_contract(emb)
    result = await emb.embed(["hello", "world"])
    assert result.provenance.provider == "openai"
    assert result.provenance.dims == 2
    assert emb.model_info().provider == "openai"
    health = await emb.health_check()
    assert health.ok


async def test_profile_builds_generic_chat_and_embedding_backends(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        ref = await put_secret(session, user.id, contract.CANARY)
        profile = await create_profile(
            session,
            user.id,
            name="local-server",
            chat_backend="openai",
            chat_model="llama-3.1-8b-instruct",
            embedding_backend="openai",
            embedding_model="local-embed",
            chat_secret_ref=ref,
            config={"base_url": "http://127.0.0.1:1234/v1"},
        )
        built_chat = await build_chat_backend(session, profile)
        built_emb = await build_embedding_backend(session, profile)
        blob = json.dumps(profile_to_dict(profile))
    assert isinstance(built_chat, OpenAICompatibleChatBackend)
    assert built_chat.backend_key == "openai"
    assert str(built_chat._client.base_url).rstrip("/") == "http://127.0.0.1:1234/v1"
    assert isinstance(built_emb, OpenAICompatibleEmbeddingBackend)
    assert built_emb.backend_key == "openai"
    assert contract.CANARY not in blob
