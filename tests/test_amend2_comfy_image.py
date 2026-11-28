"""Amendment 2 battery: ComfyUI provider + AI-composed prompts.

Transport and backend are injected fakes at the seams this module
declares (the live end-to-end proof is recorded in the campaign
state log); everything else -- the workflow graph, the history
polling, the composition call shape, the log line -- is the real
code under test."""
import asyncio
import json

import pytest

from runmal.backends.events import Done, TextDelta
from runmal.plugins.comfy_image import (
    ComfyConfig,
    ComfyUIProvider,
    chroma_workflow,
    compose_image_prompt,
    load_comfy_config,
)
from runmal.plugins.image_generation import ImageRequest, render_deterministic_png


def _config(tmp_path, **over):
    cfg = ComfyConfig(base_url="http://comfy.test:8188", **over)
    return cfg


def test_workflow_is_the_house_chroma_graph():
    wf = chroma_workflow("a prompt", "neg", 42, 832, 1216, config=_config(None))
    assert wf["1"]["class_type"] == "UNETLoader"
    assert wf["1"]["inputs"]["unet_name"] == "Chroma1-HD.safetensors"
    assert wf["2"]["inputs"]["type"] == "chroma"
    assert wf["5"]["inputs"]["text"] == "a prompt"
    assert wf["7"]["inputs"]["cfg"] == 3.0
    assert wf["9"]["inputs"]["steps"] == 40
    assert wf["10"]["inputs"]["noise_seed"] == 42
    assert wf["11"]["inputs"]["width"] == 832
    assert wf["14"]["inputs"]["filename_prefix"] == "runmal"


def test_config_comes_from_data_file_not_code(tmp_path):
    (tmp_path / "comfy_image.json").write_text(json.dumps({
        "base_url": "http://192.0.2.10:8189", "model": "Other.safetensors",
        "steps": 28}), encoding="utf-8")
    cfg = load_comfy_config(tmp_path)
    assert cfg.base_url == "http://192.0.2.10:8189"
    assert cfg.model == "Other.safetensors"
    assert cfg.steps == 28
    assert cfg.cfg == 3.0  # model-card default survives


def test_unconfigured_provider_refuses_plainly():
    with pytest.raises(ValueError, match="not configured"):
        ComfyUIProvider(ComfyConfig(base_url=""))


def test_provider_queues_polls_and_fetches():
    png = render_deterministic_png("x", "", 1, 16)
    calls = {}

    def post_json(url, payload, timeout):
        calls["post"] = (url, payload)
        return {"prompt_id": "pid-1"}

    def get_json(url, payload, timeout):
        calls.setdefault("history", []).append(url)
        return {"pid-1": {"status": {"status_str": "success"},
                          "outputs": {"14": {"images": [{
                              "filename": "runmal_00001_.png",
                              "subfolder": "", "type": "output"}]}}}}

    def get_bytes(url, timeout):
        calls["view"] = url
        return png

    provider = ComfyUIProvider(_config(None), post_json=post_json,
                               get_json=get_json, get_bytes=get_bytes,
                               poll_seconds=0)
    result = asyncio.run(provider.generate(
        ImageRequest(prompt="a fjord at dawn", width=832, height=1216, seed=7)))
    assert result.provider == "comfyui"
    assert result.road == "comfyui_diffusion"
    assert result.data == png
    assert calls["post"][0].endswith("/prompt")
    assert calls["view"].endswith("filename=runmal_00001_.png&subfolder=&type=output")


class _FakeBackend:
    backend_key = "fake"

    def __init__(self, text):
        self._text = text
        self.seen = None

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        self.seen = messages
        yield TextDelta(text=self._text)
        yield Done(reason="stop")


def test_compose_uses_backend_and_context():
    backend = _FakeBackend("A tall Norse woman stands on worn floorboards.")
    composed = asyncio.run(compose_image_prompt(
        backend, trigger="draw her",
        character_name="Groa", character_description="raven hair, pale blue eyes",
        recent_messages=[{"role": "user", "content": "She enters the longhouse."}]))
    assert composed.startswith("A tall Norse woman")
    sent = "\n".join(m.content for m in backend.seen)
    assert "draw her" in sent and "Groa" in sent and "longhouse" in sent


def test_compose_empty_is_an_error_not_a_fallback():
    backend = _FakeBackend("   ")
    with pytest.raises(Exception, match="empty image prompt"):
        asyncio.run(compose_image_prompt(backend, trigger="draw her"))
