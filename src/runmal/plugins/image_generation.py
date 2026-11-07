"""Image Generation plugin (P-087): prompt-from-scene + manual.

Roadmap line: "Image Generation plugin: prompt-from-scene +
manual, local diffusion endpoints first (Part X consumes for
avatars)."

A first-class P-081 citizen (pattern: P-084/P-085) that turns
an explicit, inspectable prompt into an image through a
provider-pluggable seam, and lands the result through the
founding P-023 asset machinery when the chat is bound to a
character.

Prompt-from-scene is EXTRACTIVE and DETERMINISTIC
(``extractive-scene-1``, the P-073 honesty pattern): the
derived prompt is assembled from the chat's own recent
messages and names, returned for inspection and editing
BEFORE any generation, and nothing in it is invented. Manual
prompts are first-class: the caller may always supply or edit
the prompt instead.

Provider honesty: generation runs ONLY through the app's own
configured provider stack -- a LOCAL diffusion endpoint
(loopback only; the provider refuses any non-loopback URL, so
no code path reaches the external network) or, when no
endpoint is configured, a deterministic local test provider
(:class:`DeterministicImageProvider`, model ``hash-canvas-1``)
that renders a real PNG whose pixels derive from the prompt
hash. Every generation record names its road --
``local_diffusion`` or ``deterministic_local`` -- plus the
provider, model and endpoint that truly produced it; the
deterministic fallback is labelled, never disguised as
diffusion. Provider bytes are sniffed before they count as a
generation: bytes that are not a recognisable image fail
loudly and record nothing.

Per-chat enablement: generation is opt-in PER CHAT and never
automatic. The citizen declares ``chat.created`` (a deliberate
no-op) and subscribes to no message events: appending a
message never generates anything. Enablement lives in the
plugin instance (process-local, like the P-081 registry
itself); :func:`generate_image` refuses a chat that is not
enabled with :class:`ChatNotEnabledError`.

Asset landing (P-023): assets are character-scoped, so a
generation lands through ``assets.service.add_asset``
(kind ``background``) only when the chat is bound to a
character. A chat with no bound character still generates;
its record states ``landed=False`` with reason
``no_character_bound`` -- plainly, never silently. A landing
failure likewise degrades the record (``landing_error`` names
the exception type) without un-generating the image.

Sandbox stance (P-082): only v1 surface permissions are
declared, so the derived resource grant set is EMPTY
(:func:`sandbox_grants` proves it). Providers and the session
factory are host-supplied wiring handed to trusted in-tree
registration code, not plugin resource grants; the local
provider's loopback refusal is defence in depth on top.

Wiring: :func:`register_plugin` only. ``build_registry`` /
``create_app`` are unchanged (P-081 pins the empty boot
registry); P-086 banks before this slice and the keeper
reconciles liveness at banking. No migration: enablement and
the generation ledger are process-local, and landed images
ride the founding P-023 tables. See
docs/IMAGE_GENERATION_PLUGIN_2026-11-07.md.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import struct
import urllib.request
import zlib
from dataclasses import dataclass
from urllib.parse import urlparse

from runmal.assets.imaging import sniff_image
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers
from runmal.prompt.slots import Slot
from runmal.sandbox.policy import grants_from_manifest

PLUGIN_ID = "runmal.image-generation"
PLUGIN_VERSION = "1.0.0"
HOOK_ID = "image-scene"
SLOT_LOCAL_ID = "generated-image"
UI_LOCAL_ID = "image-panel"
SCENE_GENERATOR = "extractive-scene-1"
DETERMINISTIC_PROVIDER = "deterministic-local"
DETERMINISTIC_MODEL = "hash-canvas-1"
ROAD_LOCAL = "local_diffusion"
ROAD_DETERMINISTIC = "deterministic_local"
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512
DEFAULT_CANVAS = 64
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_PROMPT_CHARS = 1000
SCENE_MESSAGE_WINDOW = 6
SCENE_SEGMENT_CHARS = 120
DECLARED_EVENTS = ("chat.created",)
_LOOPBACK_HOSTS = frozenset({"localhost", "::1"})
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ImageGenError(ValueError):
    """Base for this citizen's typed refusals."""


class ChatNotEnabledError(ImageGenError):
    """Generation was asked for a chat that is not enabled."""


class ImageProviderError(ImageGenError):
    """A provider failed, or returned bytes that are no image."""


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _collapse(text):
    return " ".join(str(text or "").split())


def _slug(text, limit=48):
    slug = _SLUG_RE.sub("-", str(text or "").lower()).strip("-")
    return slug[:limit].rstrip("-") or "generated-image"


@dataclass(frozen=True)
class ImageGenConfig:
    endpoint: str = ""
    model: str = ""
    default_width: int = DEFAULT_WIDTH
    default_height: int = DEFAULT_HEIGHT
    canvas_size: int = DEFAULT_CANVAS
    timeout_seconds: int = DEFAULT_TIMEOUT
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS

    def __post_init__(self):
        if not isinstance(self.endpoint, str):
            raise ValueError(f"endpoint must be a string: {self.endpoint!r}")
        if not isinstance(self.model, str):
            raise ValueError(f"model must be a string: {self.model!r}")
        for name in ("default_width", "default_height"):
            value = getattr(self, name)
            if not _is_int(value) or not 64 <= value <= 2048:
                raise ValueError(f"{name} must be an int in 64..2048: {value!r}")
        if not _is_int(self.canvas_size) or not 16 <= self.canvas_size <= 256:
            raise ValueError(f"canvas_size must be an int in 16..256: {self.canvas_size!r}")
        if not _is_int(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 300:
            raise ValueError(f"timeout_seconds must be an int in 1..300: {self.timeout_seconds!r}")
        if not _is_int(self.max_prompt_chars) or not 100 <= self.max_prompt_chars <= 4000:
            raise ValueError(
                f"max_prompt_chars must be an int in 100..4000: {self.max_prompt_chars!r}"
            )


def manifest_data():
    return {
        "id": PLUGIN_ID,
        "name": "Image Generation",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": (
            "Prompt-from-scene and manual image generation through local diffusion endpoints first."
        ),
        "author": "Runmal",
        "capabilities": ["chat.events", "prompt.hooks", "ui.slots"],
        "permissions": ["chat.read", "prompt.inject", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [{"id": HOOK_ID, "stage": "slots", "priority": 80}],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.sidebar",
                "label": "Image Generation",
                "order": 80,
                "payload": {"kind": "panel", "route": "image-generation"},
            }
        ],
        "settings": {
            "schema": {
                "default_width": {"type": "integer", "minimum": 64, "maximum": 2048},
                "default_height": {"type": "integer", "minimum": 64, "maximum": 2048},
                "endpoint": {"type": "string"},
                "model": {"type": "string"},
            },
            "defaults": {
                "default_width": DEFAULT_WIDTH,
                "default_height": DEFAULT_HEIGHT,
                "endpoint": "",
                "model": "",
            },
        },
        "enabled_by_default": False,
    }


def build_manifest():
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest):
    defaults = {}
    if isinstance(manifest.settings, dict):
        raw = manifest.settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    width = defaults.get("default_width", DEFAULT_WIDTH)
    if not _is_int(width) or not 64 <= width <= 2048:
        width = DEFAULT_WIDTH
    height = defaults.get("default_height", DEFAULT_HEIGHT)
    if not _is_int(height) or not 64 <= height <= 2048:
        height = DEFAULT_HEIGHT
    endpoint = defaults.get("endpoint", "")
    if not isinstance(endpoint, str):
        endpoint = ""
    model = defaults.get("model", "")
    if not isinstance(model, str):
        model = ""
    return ImageGenConfig(
        endpoint=endpoint, model=model, default_width=width, default_height=height
    )


def sandbox_grants():
    return grants_from_manifest(manifest_to_data(build_manifest()))


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    seed: int = 0

    def __post_init__(self):
        if not _collapse(self.prompt):
            raise ValueError("prompt must be non-empty")
        for name in ("width", "height"):
            value = getattr(self, name)
            if not _is_int(value) or not 16 <= value <= 4096:
                raise ValueError(f"{name} must be an int in 16..4096: {value!r}")
        if not _is_int(self.seed):
            raise ValueError(f"seed must be an int: {self.seed!r}")


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    provider: str
    model: str
    endpoint: str | None
    road: str


def _png_chunk(ctype, payload):
    chunk = struct.pack(">I", len(payload)) + ctype + payload
    return chunk + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)


def render_deterministic_png(prompt, negative_prompt, seed, size):
    """A real PNG whose pixels derive from the request hash.

    RGB, bit depth 8, filter-0 rows: exactly the subset
    runmal.assets.imaging decodes, so P-023 thumbnails work.
    A horizontal gradient between two hash-derived colours,
    overlaid with a hash-derived block grid. Same request,
    identical bytes (the battery pins it).
    """
    digest = hashlib.sha256(f"{prompt}|{negative_prompt}|{seed}".encode()).digest()
    c1 = tuple(digest[0:3])
    c2 = tuple(digest[3:6])
    blocks = max(2, size // 16)
    cell = size / blocks
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")
        by = int(y // cell)
        for x in range(size):
            t = x / max(1, size - 1)
            base = tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            idx = digest[6 + ((by * blocks + int(x // cell)) % 26)]
            if idx % 3 == 0:
                base = tuple((v + idx) % 256 for v in base)
            row.extend(base)
        rows.append(bytes(row))
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    idat = _png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + _png_chunk(b"IEND", b"")


class DeterministicImageProvider:
    """The deterministic local test road (never diffusion)."""

    provider_id = DETERMINISTIC_PROVIDER
    model = DETERMINISTIC_MODEL
    endpoint = None
    road = ROAD_DETERMINISTIC

    def __init__(self, canvas_size=DEFAULT_CANVAS):
        if not _is_int(canvas_size) or not 16 <= canvas_size <= 256:
            raise ValueError(f"canvas_size must be an int in 16..256: {canvas_size!r}")
        self.canvas_size = canvas_size

    async def generate(self, request):
        data = render_deterministic_png(
            request.prompt, request.negative_prompt, request.seed, self.canvas_size
        )
        return GeneratedImage(
            data=data, provider=self.provider_id, model=self.model, endpoint=None, road=self.road
        )


def is_loopback_endpoint(endpoint):
    if not isinstance(endpoint, str) or not endpoint.strip():
        return False
    parsed = urlparse(endpoint)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def _urllib_transport(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get_content_type(), resp.read()


class LocalDiffusionProvider:
    """A local diffusion endpoint, loopback only, injected transport.

    Speaks the common local txt2img JSON shape: POST
    {prompt, negative_prompt, width, height, seed}; accepts
    {images: [base64, ...]}, {image: base64} or raw image
    bytes back. The transport is host wiring: tests inject a
    fake, production uses urllib in a worker thread. No
    transport is ever pointed off-loopback -- the constructor
    refuses such an endpoint before any call exists.
    """

    road = ROAD_LOCAL

    def __init__(self, endpoint, model="", transport=None, timeout_seconds=DEFAULT_TIMEOUT):
        if not is_loopback_endpoint(endpoint):
            raise ValueError(
                f"local diffusion endpoint must be a loopback http(s) URL: {endpoint!r}"
            )
        self.endpoint = endpoint
        self.provider_id = "local-diffusion"
        self.model = model or "local-diffusion"
        self._transport = transport or _urllib_transport
        self.timeout_seconds = timeout_seconds

    async def generate(self, request):
        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
        }
        try:
            status, content_type, body = await asyncio.to_thread(
                self._transport, self.endpoint, payload, self.timeout_seconds
            )
        except ImageProviderError:
            raise
        except Exception as exc:
            raise ImageProviderError(
                f"local diffusion transport failed: {type(exc).__name__}"
            ) from exc
        if status != 200:
            raise ImageProviderError(f"local diffusion endpoint returned HTTP {status}")
        data = self._extract(body, content_type)
        if data is None:
            raise ImageProviderError("local diffusion endpoint returned no image")
        return GeneratedImage(
            data=data,
            provider=self.provider_id,
            model=self.model,
            endpoint=self.endpoint,
            road=self.road,
        )

    @staticmethod
    def _extract(body, content_type):
        if content_type and content_type.startswith("image/"):
            return body
        try:
            doc = json.loads(body)
        except (ValueError, TypeError):
            return body or None
        if isinstance(doc, dict):
            images = doc.get("images")
            if isinstance(images, list) and images and isinstance(images[0], str):
                try:
                    return base64.b64decode(images[0])
                except ValueError:
                    return None
            single = doc.get("image") or doc.get("data")
            if isinstance(single, str) and single:
                try:
                    return base64.b64decode(single)
                except ValueError:
                    return None
        return None


def build_provider(config):
    """The configured provider: local endpoint first, else the
    deterministic local test road (assignment order)."""
    if config.endpoint:
        return LocalDiffusionProvider(
            config.endpoint, model=config.model, timeout_seconds=config.timeout_seconds
        )
    return DeterministicImageProvider(canvas_size=config.canvas_size)


def derive_scene_prompt(
    messages, character_name=None, chat_title=None, *, max_chars=DEFAULT_MAX_PROMPT_CHARS
):
    """Derive an image prompt from the current scene (pure).

    Extractive: the subject is the character name (else the
    chat title); segments are the first sentence of each of
    the last SCENE_MESSAGE_WINDOW non-empty messages, capped
    per segment. Returns the inspectable derivation -- callers
    show it, edit it, or pass it on; nothing here generates.
    """
    subject = _collapse(character_name) or _collapse(chat_title)
    texts = []
    for message in messages or []:
        if isinstance(message, dict):
            role, content = message.get("role", ""), message.get("content", "")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")
        text = _collapse(content)
        if text:
            texts.append((str(role or ""), text))
    segments = []
    sources = []
    for role, text in texts[-SCENE_MESSAGE_WINDOW:]:
        found = _SENTENCE_RE.findall(text)
        segment = _collapse(found[0]) if found else text
        if len(segment) > SCENE_SEGMENT_CHARS:
            segment = segment[: SCENE_SEGMENT_CHARS - 1].rstrip(" ,;:-") + "\u2026"
        if segment:
            segments.append(segment)
            sources.append(role)
    parts = ([subject] if subject else []) + segments
    prompt = ". ".join(parts)
    if len(prompt) > max_chars:
        prompt = prompt[: max_chars - 1].rstrip(" ,;:-") + "\u2026"
    return {
        "prompt": prompt,
        "subject": subject,
        "segments": segments,
        "sources": sources,
        "message_count": len(texts),
        "generator": SCENE_GENERATOR,
    }


def normalise_manual_prompt(prompt, *, max_chars=DEFAULT_MAX_PROMPT_CHARS):
    text = _collapse(prompt)
    if not text:
        raise ValueError("manual prompt must be non-empty")
    if len(text) > max_chars:
        raise ValueError(f"manual prompt exceeds {max_chars} chars: {len(text)}")
    return text


_HEADER = "Latest generated image for this chat (inspectable; road and provider named):"


class ImageGenerationPlugin:
    """The citizen: per-chat enablement + ledger + the scene slot.

    ``session_factory`` / ``provider`` are host bootstrap
    wiring (trusted in-tree code binds them at registration);
    with no factory the hook abstains quietly, and with no
    explicit provider the configured one is built lazily.
    """

    def __init__(self, session_factory=None, provider=None, config=None):
        self._session_factory = session_factory
        self._provider = provider
        self.config = config or config_from_manifest(build_manifest())
        self._enabled_chats = set()
        self._ledger = []
        self._counter = 0

    @property
    def manifest(self):
        return build_manifest()

    @property
    def provider(self):
        if self._provider is None:
            self._provider = build_provider(self.config)
        return self._provider

    def bind_session_factory(self, session_factory):
        self._session_factory = session_factory

    def bind_provider(self, provider):
        self._provider = provider

    def set_chat_enabled(self, chat_id, enabled=True):
        if not isinstance(chat_id, str) or not chat_id:
            raise ValueError(f"chat_id must be a non-empty string: {chat_id!r}")
        if enabled:
            self._enabled_chats.add(chat_id)
        else:
            self._enabled_chats.discard(chat_id)
        return chat_id in self._enabled_chats

    def is_chat_enabled(self, chat_id):
        return chat_id in self._enabled_chats

    def enabled_chat_ids(self):
        return sorted(self._enabled_chats)

    def record_generation(self, record):
        self._counter += 1
        full = {"id": f"gen-{self._counter:04d}", **record}
        self._ledger.append(full)
        return full

    def history(self, chat_id=None):
        return [dict(r) for r in self._ledger if chat_id is None or r["chat_id"] == chat_id]

    def latest(self, chat_id):
        rows = [r for r in self._ledger if r["chat_id"] == chat_id]
        return dict(rows[-1]) if rows else None

    def handlers(self):
        return PluginHandlers(on_event=self.on_event, prompt_hooks={HOOK_ID: self.image_slot})

    async def on_event(self, event):
        """Deliberate no-op: generation is explicit, never
        auto-fired by chat or message events."""
        return None

    async def image_slot(self, ctx, slots):
        if ctx.chat_id is None or not self.is_chat_enabled(ctx.chat_id):
            return None
        latest = self.latest(ctx.chat_id)
        if latest is None:
            return None
        asset = latest["asset_id"] or f"unlanded ({latest['landing_reason']})"
        content = (
            f"{_HEADER}\n{latest['id']}: "
            f'"{latest["prompt"][:120]}" via {latest["road"]} '
            f"({latest['provider']}/{latest['model']}), asset {asset}."
        )
        return [
            Slot(
                id=SLOT_LOCAL_ID,
                kind="generated_image",
                role="system",
                content=content,
                order=4,
                priority=80,
                trigger="image-generation",
            )
        ]


async def preview_scene_prompt(session, user_id, chat_id, *, plugin):
    """The inspectable scene derivation for one chat; generates
    nothing. Owner-scoped: None for a missing/not-owned chat."""
    from runmal.characters.service import get_character
    from runmal.chats.service import get_chat, get_history

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    messages = await get_history(session, user_id, chat_id)
    character_name = None
    if chat.character_id:
        character = await get_character(session, user_id, chat.character_id)
        if character is not None:
            character_name = character.name
    derived = derive_scene_prompt(
        list(messages or []),
        character_name=character_name,
        chat_title=chat.title,
        max_chars=plugin.config.max_prompt_chars,
    )
    return {
        "plugin_id": PLUGIN_ID,
        "chat_id": chat_id,
        "enabled": plugin.is_chat_enabled(chat_id),
        **derived,
    }


async def generate_image(
    session,
    user_id,
    chat_id,
    *,
    plugin,
    prompt=None,
    negative_prompt="",
    seed=None,
    width=None,
    height=None,
):
    """Generate one image for an enabled chat; returns the
    ledger record. None for a missing/not-owned chat; raises
    ChatNotEnabledError when the chat is not enabled, ValueError
    for an empty prompt, ImageProviderError for provider trouble.
    Landing through P-023 commits (add_asset's own contract)."""
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if not plugin.is_chat_enabled(chat_id):
        raise ChatNotEnabledError(
            f"image generation is not enabled for chat {chat_id!r}; enable it per-chat first"
        )
    if prompt is not None:
        final_prompt = normalise_manual_prompt(prompt, max_chars=plugin.config.max_prompt_chars)
        prompt_source = "manual"
    else:
        preview = await preview_scene_prompt(session, user_id, chat_id, plugin=plugin)
        final_prompt = (preview or {}).get("prompt", "")
        if not final_prompt:
            raise ValueError("scene derivation produced an empty prompt; supply a manual prompt")
        prompt_source = "scene"
    request = ImageRequest(
        prompt=final_prompt,
        negative_prompt=_collapse(negative_prompt),
        width=width or plugin.config.default_width,
        height=height or plugin.config.default_height,
        seed=0 if seed is None else seed,
    )
    generated = await plugin.provider.generate(request)
    info = sniff_image(generated.data)
    if info.format == "unknown" or info.error:
        raise ImageProviderError(
            f"provider {generated.provider!r} returned bytes that are "
            f"not a recognisable image (format={info.format!r}, "
            f"error={info.error!r})"
        )
    record = {
        "chat_id": chat_id,
        "prompt": final_prompt,
        "prompt_source": prompt_source,
        "negative_prompt": request.negative_prompt,
        "seed": request.seed,
        "width": request.width,
        "height": request.height,
        "provider": generated.provider,
        "model": generated.model,
        "endpoint": generated.endpoint,
        "road": generated.road,
        "format": info.format,
        "image_width": info.width,
        "image_height": info.height,
        "byte_size": len(generated.data),
        "sha256": hashlib.sha256(generated.data).hexdigest(),
        "asset_id": None,
        "landed": False,
        "landing_reason": "",
        "landing_error": "",
    }
    if not chat.character_id:
        record["landing_reason"] = "no_character_bound"
    else:
        from runmal.assets import service as assets_service

        filename = (
            f"generated-{record['sha256'][:12]}.png"
            if info.format == "png"
            else f"generated-{record['sha256'][:12]}.{info.format}"
        )
        try:
            row = await assets_service.add_asset(
                session,
                user_id,
                chat.character_id,
                kind="background",
                name=_slug(final_prompt),
                filename=filename,
                data=generated.data,
            )
            record["asset_id"] = row.id
            record["landed"] = True
            record["landing_reason"] = "character_asset"
        except Exception as exc:
            record["landing_reason"] = "landing_failed"
            record["landing_error"] = type(exc).__name__
    return plugin.record_generation(record)


async def image_status(session, user_id, chat_id, *, plugin):
    """The inspectable per-chat state. Owner-scoped: None for
    a missing/not-owned chat."""
    from runmal.chats.service import get_chat

    chat = await get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    provider = plugin.provider
    rows = plugin.history(chat_id)
    return {
        "plugin_id": PLUGIN_ID,
        "chat_id": chat_id,
        "character_id": chat.character_id,
        "enabled": plugin.is_chat_enabled(chat_id),
        "provider": getattr(provider, "provider_id", type(provider).__name__),
        "model": getattr(provider, "model", ""),
        "endpoint": getattr(provider, "endpoint", None),
        "road": getattr(provider, "road", ""),
        "generation_count": len(rows),
        "latest": rows[-1] if rows else None,
    }


def register_plugin(registry, session_factory=None, *, provider=None, config=None, enable=False):
    """Register the citizen into ``registry`` (trusted code only).

    Returns the record and the plugin instance. ``enable=True``
    performs the owner's enable verb immediately; per-chat
    enablement is separate (plugin.set_chat_enabled)."""
    plugin = ImageGenerationPlugin(session_factory, provider, config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS",
    "DETERMINISTIC_MODEL",
    "DETERMINISTIC_PROVIDER",
    "HOOK_ID",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "ROAD_DETERMINISTIC",
    "ROAD_LOCAL",
    "SCENE_GENERATOR",
    "SLOT_LOCAL_ID",
    "UI_LOCAL_ID",
    "ChatNotEnabledError",
    "DeterministicImageProvider",
    "GeneratedImage",
    "ImageGenConfig",
    "ImageGenError",
    "ImageGenerationPlugin",
    "ImageProviderError",
    "ImageRequest",
    "LocalDiffusionProvider",
    "build_manifest",
    "build_provider",
    "config_from_manifest",
    "derive_scene_prompt",
    "generate_image",
    "image_status",
    "is_loopback_endpoint",
    "manifest_data",
    "normalise_manual_prompt",
    "preview_scene_prompt",
    "register_plugin",
    "render_deterministic_png",
    "sandbox_grants",
]
