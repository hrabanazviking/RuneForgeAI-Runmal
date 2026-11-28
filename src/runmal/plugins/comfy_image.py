"""ComfyUI provider + AI-composed prompts for image generation (Amendment 2).

Why this module exists: the P-087 plugin's own diffusion provider
(:class:`runmal.plugins.image_generation.LocalDiffusionProvider`)
speaks a generic txt2img JSON shape and refuses every non-loopback
endpoint, so it cannot reach the house picture computer at all --
ComfyUI speaks a workflow-graph API (``POST /prompt``, poll
``/history/{id}``, fetch ``/view``), and in this house it lives on
another machine, reached over the tailnet. This module is the
ComfyUI road, in the plugin's own provider shape
(:class:`GeneratedImage` in / out), plus the Amendment-2 prompt
road: when a picture is requested, the chat's connected backend
composes the image prompt from the character/scene context, and
the COMPOSED prompt -- never the raw trigger alone -- is what goes
to ComfyUI.

Configuration is data, never code literals (house Law 7): the
ComfyUI base URL and generation settings come from
``comfy_image.json`` in the Rúnmál data dir
(``RUNMAL_DATA_DIR``-aware), with ``RUNMAL_COMFYUI_URL`` as an
environment override for the base URL only. No address is written
anywhere in this file.

Every composed generation appends one JSON line to
``image_generation_log.jsonl`` in the data dir, carrying BOTH the
triggering user text and the composed prompt, plus the provider
record -- the inspectable proof of which prompt truly drew.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from runmal.backends.events import TextDelta
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.plugins.image_generation import GeneratedImage, ImageProviderError

CONFIG_FILENAME = "comfy_image.json"
LOG_FILENAME = "image_generation_log.jsonl"
ROAD_COMFYUI = "comfyui_diffusion"
PROVIDER_ID = "comfyui"

# House Chroma1-HD model-card recipe (skill: chroma-image-making):
# 40 steps, CFG 3.0, euler over a Beta scheduler, T5-XXL + FLUX VAE.
DEFAULT_MODEL = "Chroma1-HD.safetensors"
DEFAULT_CLIP = "t5xxl_fp16.safetensors"
DEFAULT_VAE = "ae.safetensors"
DEFAULT_STEPS = 40
DEFAULT_CFG = 3.0
DEFAULT_SHIFT = 1.0
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216
DEFAULT_NEGATIVE = "text, watermark, duplicate person, cropped hands, cropped feet"
DEFAULT_TIMEOUT = 900


def _data_dir() -> Path:
    from runmal.auth import data_dir

    return data_dir()


@dataclass(frozen=True)
class ComfyConfig:
    base_url: str = ""
    model: str = DEFAULT_MODEL
    clip: str = DEFAULT_CLIP
    vae: str = DEFAULT_VAE
    steps: int = DEFAULT_STEPS
    cfg: float = DEFAULT_CFG
    shift: float = DEFAULT_SHIFT
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    negative_prompt: str = DEFAULT_NEGATIVE
    timeout_seconds: int = DEFAULT_TIMEOUT


def load_comfy_config(data_dir=None) -> ComfyConfig:
    """Read ``comfy_image.json`` from the data dir (missing file =
    unconfigured: empty base_url, and the provider refuses plainly)."""
    base = Path(data_dir) if data_dir else _data_dir()
    raw = {}
    path = base / CONFIG_FILENAME
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                raw = doc
        except (ValueError, OSError):
            raw = {}
    base_url = os.environ.get("RUNMAL_COMFYUI_URL") or raw.get("base_url") or ""
    if not isinstance(base_url, str):
        base_url = ""

    def _str(key, default):
        value = raw.get(key)
        return value if isinstance(value, str) and value else default

    def _int(key, default):
        value = raw.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    def _num(key, default):
        value = raw.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default

    return ComfyConfig(
        base_url=base_url.rstrip("/"),
        model=_str("model", DEFAULT_MODEL),
        clip=_str("clip", DEFAULT_CLIP),
        vae=_str("vae", DEFAULT_VAE),
        steps=_int("steps", DEFAULT_STEPS),
        cfg=_num("cfg", DEFAULT_CFG),
        shift=_num("shift", DEFAULT_SHIFT),
        width=_int("width", DEFAULT_WIDTH),
        height=_int("height", DEFAULT_HEIGHT),
        negative_prompt=_str("negative_prompt", DEFAULT_NEGATIVE),
        timeout_seconds=_int("timeout_seconds", DEFAULT_TIMEOUT),
    )


def chroma_workflow(positive, negative, seed, width, height, *, config):
    """The Chroma ComfyUI graph (API format) -- the same graph the
    Saga portrait painter uses, model-card recipe."""
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": config.model, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": config.clip, "type": "chroma", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": config.vae}},
        "4": {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": ["1", 0], "shift": config.shift}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": positive}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": negative}},
        "7": {"class_type": "CFGGuider",
              "inputs": {"model": ["4", 0], "positive": ["5", 0],
                         "negative": ["6", 0], "cfg": config.cfg}},
        "8": {"class_type": "KSamplerSelect",
              "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "BetaSamplingScheduler",
              "inputs": {"model": ["4", 0], "steps": config.steps,
                         "alpha": 0.45, "beta": 0.45}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": width, "height": height, "batch_size": 1}},
        "12": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["10", 0], "guider": ["7", 0],
                          "sampler": ["8", 0], "sigmas": ["9", 0],
                          "latent_image": ["11", 0]}},
        "13": {"class_type": "VAEDecode",
               "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage",
               "inputs": {"images": ["13", 0], "filename_prefix": "runmal"}},
    }


def _http_json(url, payload=None, timeout=60):
    if payload is None:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_bytes(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


class ComfyUIProvider:
    """The plugin-shaped provider over the house ComfyUI road.

    Transport is injectable for the battery; production uses urllib
    in a worker thread. Unlike the loopback-only local provider,
    this road's endpoint comes from operator config (the tailnet
    picture computer) -- it is host wiring, never a code literal.
    """

    provider_id = PROVIDER_ID
    road = ROAD_COMFYUI

    def __init__(self, config, *, post_json=None, get_json=None, get_bytes=None,
                 poll_seconds=2.0):
        if not config.base_url:
            raise ValueError(
                "ComfyUI base_url is not configured: set base_url in "
                f"{CONFIG_FILENAME} in the data dir or RUNMAL_COMFYUI_URL")
        self.config = config
        self.endpoint = config.base_url
        self.model = config.model
        self._post_json = post_json or _http_json
        self._get_json = get_json or _http_json
        self._get_bytes = get_bytes or _http_bytes
        self._poll_seconds = poll_seconds

    async def generate(self, request):
        workflow = chroma_workflow(
            request.prompt, request.negative_prompt or self.config.negative_prompt,
            request.seed, request.width, request.height, config=self.config)
        payload = {"prompt": workflow, "client_id": uuid.uuid4().hex}
        try:
            queued = await asyncio.to_thread(
                self._post_json, f"{self.endpoint}/prompt", payload, 60)
        except Exception as exc:
            raise ImageProviderError(
                f"ComfyUI queue failed: {type(exc).__name__}") from exc
        prompt_id = queued.get("prompt_id") if isinstance(queued, dict) else None
        if not prompt_id:
            raise ImageProviderError(f"ComfyUI did not queue the job: {queued!r}")
        deadline = time.time() + self.config.timeout_seconds
        image_ref = None
        while time.time() < deadline:
            history = await asyncio.to_thread(
                self._get_json, f"{self.endpoint}/history/{prompt_id}", None, 30)
            entry = (history or {}).get(prompt_id) or {}
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ImageProviderError(
                    f"ComfyUI job failed: {status.get('messages')}")
            for node_out in (entry.get("outputs") or {}).values():
                images = node_out.get("images") or []
                if images:
                    image_ref = images[0]
                    break
            if image_ref:
                break
            await asyncio.sleep(self._poll_seconds)
        if not image_ref:
            raise ImageProviderError("ComfyUI job timed out before an image landed")
        query = urllib.parse.urlencode({
            "filename": image_ref.get("filename", ""),
            "subfolder": image_ref.get("subfolder", ""),
            "type": image_ref.get("type", "output"),
        })
        try:
            data = await asyncio.to_thread(
                self._get_bytes, f"{self.endpoint}/view?{query}", 120)
        except Exception as exc:
            raise ImageProviderError(
                f"ComfyUI image fetch failed: {type(exc).__name__}") from exc
        return GeneratedImage(
            data=data, provider=self.provider_id, model=self.model,
            endpoint=self.endpoint, road=self.road)


COMPOSE_SYSTEM = (
    "You compose image-generation prompts for a Chroma text-to-image model. "
    "Write ONE prompt only: a natural-language scene description of 60-140 "
    "words describing what the camera sees -- subject, action or pose, place "
    "and time, framing, light, materials, and finish. For a full-body figure, "
    "state head-to-toe framing and end with what is worn or borne at the feet "
    "and the surface the figure stands on. No preamble, no quotes, no lists."
)


async def compose_image_prompt(backend, *, trigger, character_name="",
                               character_description="", recent_messages=()):
    """Ask the connected chat backend to compose the image prompt
    from the character/scene context. Returns the composed text;
    raises on an empty composition (never silently falls back to
    the raw trigger -- the caller decides, and the log says which)."""
    context = []
    if character_name:
        context.append(f"Character: {character_name}")
    if character_description:
        context.append(f"Character description: {character_description}")
    for message in list(recent_messages or [])[-6:]:
        if isinstance(message, dict):
            role, content = message.get("role", ""), message.get("content", "")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")
        text = " ".join(str(content or "").split())
        if text:
            context.append(f"{role}: {text[:300]}")
    user = (
        "Picture requested: " + " ".join(str(trigger or "").split()) + "\n\n"
        "Scene context:\n" + ("\n".join(context) if context else "(none)")
    )
    messages = [
        ChatMessage(role="system", content=COMPOSE_SYSTEM),
        ChatMessage(role="user", content=user),
    ]
    cancel = asyncio.Event()
    parts = []
    async for event in backend.chat_stream(
            messages, SamplingParams(temperature=0.7, max_output_tokens=400), cancel):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    composed = " ".join("".join(parts).split()).strip().strip('"')
    if not composed:
        raise ImageProviderError("the chat backend composed an empty image prompt")
    return composed


def append_image_log(record, data_dir=None):
    base = Path(data_dir) if data_dir else _data_dir()
    line = json.dumps(record, ensure_ascii=False)
    with open(base / LOG_FILENAME, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return base / LOG_FILENAME


async def generate_picture_with_composed_prompt(
        session, user_id, chat_id, *, plugin, backend, trigger,
        character_name="", character_description="", recent_messages=(),
        seed=None, width=None, height=None, data_dir=None):
    """The Amendment-2 road end to end: compose via the chat
    backend, generate via the plugin's provider (the ComfyUI
    provider in production wiring), and log BOTH the trigger and
    the composed prompt alongside the generation record."""
    from runmal.plugins.image_generation import generate_image

    if width is None or height is None:
        provider_config = getattr(plugin.provider, "config", None)
        if width is None:
            width = getattr(provider_config, "width", None)
        if height is None:
            height = getattr(provider_config, "height", None)
    composed = await compose_image_prompt(
        backend, trigger=trigger, character_name=character_name,
        character_description=character_description,
        recent_messages=recent_messages)
    record = await generate_image(
        session, user_id, chat_id, plugin=plugin, prompt=composed, seed=seed,
        width=width, height=height)
    if record is not None:
        record = {**record, "prompt_source": "ai_composed",
                  "trigger": " ".join(str(trigger or "").split())}
        append_image_log({
            "chat_id": chat_id,
            "trigger": record["trigger"],
            "composed_prompt": composed,
            "prompt_source": "ai_composed",
            "provider": record.get("provider"),
            "model": record.get("model"),
            "endpoint": record.get("endpoint"),
            "road": record.get("road"),
            "seed": record.get("seed"),
            "image_width": record.get("image_width"),
            "image_height": record.get("image_height"),
            "byte_size": record.get("byte_size"),
            "sha256": record.get("sha256"),
            "asset_id": record.get("asset_id"),
            "landed": record.get("landed"),
        }, data_dir=data_dir)
    return record


__all__ = [
    "CONFIG_FILENAME",
    "LOG_FILENAME",
    "ROAD_COMFYUI",
    "ComfyConfig",
    "ComfyUIProvider",
    "append_image_log",
    "chroma_workflow",
    "compose_image_prompt",
    "generate_picture_with_composed_prompt",
    "load_comfy_config",
]
