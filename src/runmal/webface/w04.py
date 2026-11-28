"""W-04 compositions: Connections, Generation, first-run.

All over EXISTING engine roads (no new engine routes):
- backend profiles (R-02): CRUD, write-only secret tri-state
  (INV-023), health+models rendered as plain words, per-chat pin;
- presets/bundles/overrides/resolve (R-09 parity): ONE uniform
  sampler form model generated from the engine's canonical bag
  keys (presets/service.py _CANONICAL, 29 keys — verified set-
  equal in the W-04 tests); unknown keys carried verbatim;
- first-run (R-05 parity): the R-04 pure rule (zero profiles AND
  zero characters), connect -> prove -> meet -> your name.
Secrets: a key value travels once, in the secret-route body; it
is never stored on any object here, never rendered, never logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .engine import EngineError

# ------------------------------------------------------------ samplers

KIND_FLOAT = "float"
KIND_INT = "int"
KIND_STRINGS = "strings"
KIND_BIAS = "bias"


@dataclass(frozen=True)
class SamplerField:
    key: str
    label: str
    kind: str
    group: str
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False
    help: str = ""


SAMPLER_FIELDS: tuple[SamplerField, ...] = (
    SamplerField(
        "temperature",
        "Temperature (creativity)",
        KIND_FLOAT,
        "Core",
        minimum=0.0,
        help="Higher is wilder, lower is steadier.",
    ),
    SamplerField(
        "top_p",
        "Top P (nucleus cutoff)",
        KIND_FLOAT,
        "Core",
        minimum=0.0,
        maximum=1.0,
        exclusive_minimum=True,
    ),
    SamplerField("top_k", "Top K (word shortlist)", KIND_INT, "Core", minimum=0),
    SamplerField("min_p", "Min P (relative floor)", KIND_FLOAT, "Core", minimum=0.0, maximum=1.0),
    SamplerField("repetition_penalty", "Repetition penalty", KIND_FLOAT, "Penalties", minimum=0.0),
    SamplerField(
        "presence_penalty", "Presence penalty", KIND_FLOAT, "Penalties", minimum=-2.0, maximum=2.0
    ),
    SamplerField(
        "frequency_penalty", "Frequency penalty", KIND_FLOAT, "Penalties", minimum=-2.0, maximum=2.0
    ),
    SamplerField(
        "typical_p",
        "Typical P",
        KIND_FLOAT,
        "Sampling filters",
        minimum=0.0,
        maximum=1.0,
        exclusive_minimum=True,
    ),
    SamplerField("top_a", "Top A", KIND_FLOAT, "Sampling filters", minimum=0.0, maximum=1.0),
    SamplerField(
        "tfs_z",
        "Tail-free sampling (TFS Z)",
        KIND_FLOAT,
        "Sampling filters",
        minimum=0.0,
        maximum=1.0,
    ),
    SamplerField(
        "epsilon_cutoff", "Epsilon cutoff", KIND_FLOAT, "Sampling filters", minimum=0.0, maximum=1.0
    ),
    SamplerField(
        "eta_cutoff", "Eta cutoff", KIND_FLOAT, "Sampling filters", minimum=0.0, maximum=1.0
    ),
    SamplerField("dry_multiplier", "DRY multiplier", KIND_FLOAT, "DRY repetition", minimum=0.0),
    SamplerField("dry_base", "DRY base", KIND_FLOAT, "DRY repetition", minimum=1.0),
    SamplerField(
        "dry_allowed_length", "DRY allowed repeat length", KIND_INT, "DRY repetition", minimum=0
    ),
    SamplerField(
        "dry_penalty_last_n", "DRY penalty window (last N)", KIND_INT, "DRY repetition", minimum=0
    ),
    SamplerField("dry_sequence_breakers", "DRY sequence breakers", KIND_STRINGS, "DRY repetition"),
    SamplerField("xtc_probability", "XTC probability", KIND_FLOAT, "XTC", minimum=0.0, maximum=1.0),
    SamplerField("xtc_threshold", "XTC threshold", KIND_FLOAT, "XTC", minimum=0.0, maximum=1.0),
    SamplerField("mirostat_mode", "Mirostat mode", KIND_INT, "Mirostat", minimum=0, maximum=2),
    SamplerField(
        "mirostat_tau",
        "Mirostat tau (target surprise)",
        KIND_FLOAT,
        "Mirostat",
        minimum=0.0,
        exclusive_minimum=True,
    ),
    SamplerField(
        "mirostat_eta",
        "Mirostat eta (learning rate)",
        KIND_FLOAT,
        "Mirostat",
        minimum=0.0,
        exclusive_minimum=True,
    ),
    SamplerField(
        "dynamic_temperature_range",
        "Dynamic temperature range",
        KIND_FLOAT,
        "Dynamic temperature",
        minimum=0.0,
    ),
    SamplerField(
        "dynamic_temperature_exponent",
        "Dynamic temperature exponent",
        KIND_FLOAT,
        "Dynamic temperature",
        minimum=0.0,
        exclusive_minimum=True,
    ),
    SamplerField("max_tokens", "Max reply tokens", KIND_INT, "Limits & stops", minimum=1),
    SamplerField("context_length", "Context length", KIND_INT, "Limits & stops", minimum=1),
    SamplerField("seed", "Seed", KIND_INT, "Limits & stops", minimum=0),
    SamplerField("stop", "Stop sequences", KIND_STRINGS, "Limits & stops"),
    SamplerField("logit_bias", "Logit bias (token = bias)", KIND_BIAS, "Limits & stops"),
)
SAMPLER_FIELD_BY_KEY = {f.key: f for f in SAMPLER_FIELDS}
SAMPLER_GROUPS = tuple(dict.fromkeys(f.group for f in SAMPLER_FIELDS))


def sampler_form_model() -> list[dict]:
    """The uniform sampler form, as data for the page scripts."""
    return [
        {
            "key": f.key,
            "label": f.label,
            "kind": f.kind,
            "group": f.group,
            "minimum": f.minimum,
            "maximum": f.maximum,
            "exclusive_minimum": f.exclusive_minimum,
            "help": f.help,
        }
        for f in SAMPLER_FIELDS
    ]


def split_bag(bag):
    known, extra = {}, {}
    for key, value in (bag or {}).items():
        (known if key in SAMPLER_FIELD_BY_KEY else extra)[key] = value
    return known, extra


def merge_bag(known, extra):
    out = dict(extra)
    out.update(known)
    return out


def parse_sampler_form(values: dict) -> dict:
    """Parse the JS sampler form's raw values into a bag.

    ``values`` maps bag key -> raw text ('' = unset). Strings and
    bias values arrive pre-shaped by the page script as lists /
    dicts and pass through. Raises EngineError(422) in words."""
    bag: dict[str, Any] = {}
    for key, raw in (values or {}).items():
        spec = SAMPLER_FIELD_BY_KEY.get(key)
        if spec is None:
            continue  # extras ride separately, never through here
        if isinstance(raw, (list, dict)):
            if raw:
                bag[key] = raw
            continue
        text = str(raw if raw is not None else "").strip()
        if not text:
            continue
        try:
            bag[key] = int(text) if spec.kind == KIND_INT else float(text)
        except ValueError:
            raise EngineError(f"{spec.label} must be a number", status=422) from None
    problems = validate_bag(bag)
    if problems:
        raise EngineError("; ".join(problems), status=422)
    return bag


def validate_bag(bag) -> list[str]:
    problems: list[str] = []
    for key, value in (bag or {}).items():
        spec = SAMPLER_FIELD_BY_KEY.get(key)
        if spec is None:
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                problems.append(f"{key} is not a value Runmal can store")
            continue
        if spec.kind == KIND_INT:
            if not isinstance(value, int) or isinstance(value, bool):
                problems.append(f"{spec.label} must be a whole number")
                continue
        elif spec.kind == KIND_FLOAT:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{spec.label} must be a number")
                continue
        elif spec.kind == KIND_STRINGS:
            if not isinstance(value, list) or not all(isinstance(s, str) and s for s in value):
                problems.append(f"{spec.label} must be a list of non-empty lines")
                continue
        elif spec.kind == KIND_BIAS:
            if not isinstance(value, dict) or any(
                not str(k).isdigit()
                or not isinstance(v, (int, float))
                or isinstance(v, bool)
                or not -100 <= v <= 100
                for k, v in value.items()
            ):
                problems.append(
                    f"{spec.label} needs decimal token ids and biases between -100 and 100"
                )
                continue
        if spec.kind in (KIND_INT, KIND_FLOAT):
            if spec.minimum is not None:
                if spec.exclusive_minimum and not value > spec.minimum:
                    problems.append(f"{spec.label} must be above {spec.minimum:g}")
                elif not spec.exclusive_minimum and not value >= spec.minimum:
                    problems.append(f"{spec.label} must be at least {spec.minimum:g}")
            if spec.maximum is not None and not value <= spec.maximum:
                problems.append(f"{spec.label} must be at most {spec.maximum:g}")
    return problems


def value_text(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


# ------------------------------------------------------------ profiles

CHAT_BACKEND_LABELS = {
    "fake": "Demo (canned replies, not a real model)",
    "ollama": "Ollama (on this computer)",
    "openrouter": "OpenRouter (online)",
    "aesir": "Aesir (Runmal's own engine, local)",
    "openai": "OpenAI-compatible (your own server)",
}
EMBEDDING_BACKEND_LABELS = {
    "": "None (no embeddings)",
    "fake": "Demo (fake embeddings)",
    "ollama": "Ollama (on this computer)",
    "aesir": "Aesir (local)",
    "openai": "OpenAI-compatible",
}
CHAT_BACKEND_KINDS = tuple(CHAT_BACKEND_LABELS)


@dataclass(frozen=True)
class BackendOption:
    kind: str
    title: str
    blurb: str
    profile_name: str
    needs_api_key: bool = False
    needs_base_url: bool = False
    default_base_url: str = ""
    default_model: str = ""


BACKEND_OPTIONS: tuple[BackendOption, ...] = (
    BackendOption(
        "ollama",
        "Ollama - on this computer",
        "Runs models locally, free and private, if Ollama is installed. Runmal can look for "
        "it and list its models.",
        "Ollama (local)",
        needs_base_url=True,
        default_base_url="http://127.0.0.1:11434",
    ),
    BackendOption(
        "openrouter",
        "OpenRouter - online, many models",
        "One API key opens many hosted models. You paste the key once; it is stored in the "
        "secret store and never shown back.",
        "OpenRouter",
        needs_api_key=True,
    ),
    BackendOption(
        "openai",
        "OpenAI-compatible - your own server",
        "Any server that speaks the OpenAI chat shape: its address, its API key if it has "
        "one, and a model name.",
        "OpenAI-compatible",
        needs_api_key=True,
        needs_base_url=True,
    ),
    BackendOption(
        "aesir",
        "Aesir - Runmal's own local engine",
        "The project's own inference engine, when it is running on this machine. No key needed.",
        "Aesir (local)",
    ),
    BackendOption(
        "fake",
        "Demo mode - not a real model",
        "Honestly: this is not a model at all. It is a canned responder that always says "
        "the same line, so you can see how Runmal feels before connecting a real mind.",
        "Demo mode",
        default_model="fake-1",
    ),
)
_OPTIONS_BY_KIND = {o.kind: o for o in BACKEND_OPTIONS}


def backend_label(kind: str) -> str:
    return CHAT_BACKEND_LABELS.get(kind, kind or "-")


def secret_words(profile: dict) -> dict:
    """Stored/not-stored words for both keys - the ONLY secret
    information a page may ever show (INV-023)."""
    return {
        "chat": "a key is stored" if profile.get("has_chat_secret") else "no key stored",
        "embedding": "a key is stored" if profile.get("has_embedding_secret") else "no key stored",
    }


def public_profile(profile: dict) -> dict:
    """The profile shape for the browser: engine fields + words.
    The engine shape carries references + booleans only; the
    secret VALUE is never in it and never added here."""
    out = dict(profile)
    out["backend_label"] = backend_label(str(profile.get("chat_backend") or ""))
    out["is_demo"] = profile.get("chat_backend") == "fake"
    out["secret_words"] = secret_words(profile)
    out["base_url"] = str((profile.get("config") or {}).get("base_url") or "")
    return out


def plain_reason(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "the backend gave no reason"
    if cleaned.startswith("{") or cleaned.startswith("["):
        return "the backend answered with something Runmal could not read"
    return cleaned


def health_words(label: str, health: dict, models=None, models_error: str = "") -> str:
    ok = bool(health.get("ok"))
    latency = health.get("latency_ms")
    latency_words = (
        f" It answered in {latency:.0f} milliseconds." if isinstance(latency, (int, float)) else ""
    )
    if not ok:
        return (
            f"Not reachable - {label} did not answer properly: "
            f"{plain_reason(str(health.get('detail') or ''))}. "
            "Check the address or key, or try a different mind."
        )
    words = f"Reachable - {label} answered.{latency_words}"
    if models is not None:
        names = [str(m.get("model_id") or m.get("display_name") or "") for m in models]
        names = [n for n in names if n]
        if names:
            shown = ", ".join(names[:5])
            extra = f" (and {len(names) - 5} more)" if len(names) > 5 else ""
            words += f" It reports {len(names)} model(s): {shown}{extra}."
        else:
            words += " It reports no models yet."
    elif models_error:
        words += (
            f" Its model list could not be read ({plain_reason(models_error)}), "
            "but the connection itself works."
        )
    return words


def probe(engine, profile_id: str) -> dict:
    """Save-then-probe: health + models as plain words."""
    profile = engine.request("GET", f"/api/v1/backend-profiles/{profile_id}")
    profile = profile if isinstance(profile, dict) else {}
    health = engine.request("GET", f"/api/v1/backend-profiles/{profile_id}/health")
    health = health if isinstance(health, dict) else {}
    models, models_error = None, ""
    if health.get("ok"):
        try:
            payload = engine.request("GET", f"/api/v1/backend-profiles/{profile_id}/models")
            rows = payload.get("models") if isinstance(payload, dict) else None
            models = rows if isinstance(rows, list) else []
        except EngineError as exc:
            models_error = exc.message
    label = (
        f"{profile.get('name') or profile_id} - "
        f"{backend_label(str(profile.get('chat_backend') or ''))}"
    )
    names = [str(m.get("model_id") or m.get("display_name") or "") for m in (models or [])]
    return {
        "ok": bool(health.get("ok")),
        "words": health_words(label, health, models, models_error),
        "models": [n for n in names if n],
        "profile": public_profile(profile),
    }


def _apply_secret(engine, profile_id: str, kind: str, action, value) -> None:
    """Tri-state secret handling: 'leave' (or absent) touches
    nothing, 'clear' deletes, 'set' stores the given value via
    the write-only road. The value is used here and dropped."""
    if action in (None, "", "leave"):
        return
    road = f"/api/v1/backend-profiles/{profile_id}/{kind}-secret"
    if action == "clear":
        engine.request("DELETE", road)
        return
    if action == "set":
        text = str(value or "")
        if not text:
            raise EngineError(
                "a key to store cannot be empty - choose Clear to remove a stored key", status=422
            )
        engine.request("PUT", road, json_body={"value": text})
        return
    raise EngineError(f"unknown secret action: {action}", status=422)


def save_profile(engine, profile_id, body: dict) -> dict:
    """Create or update a profile, then apply the secret
    tri-states. base_url rides in config; other config keys the
    engine already holds are preserved on update."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise EngineError("the profile needs a name", status=422)
    kind = str(body.get("chat_backend") or "fake")
    if kind not in CHAT_BACKEND_LABELS:
        raise EngineError(f"unknown chat backend kind: {kind}", status=422)
    base_url = str(body.get("base_url") or "").strip()
    fields = {
        "name": name,
        "chat_backend": kind,
        "chat_model": str(body.get("chat_model") or "").strip(),
        "embedding_backend": str(body.get("embedding_backend") or ""),
        "embedding_model": str(body.get("embedding_model") or "").strip(),
        "stt_ref": str(body.get("stt_ref") or ""),
        "tts_ref": str(body.get("tts_ref") or ""),
    }
    if profile_id is None:
        payload = dict(fields)
        payload["config"] = {"base_url": base_url} if base_url else {}
        profile = engine.request("POST", "/api/v1/backend-profiles", json_body=payload)
        profile = profile if isinstance(profile, dict) else {}
        profile_id = str(profile.get("id") or "")
    else:
        current = engine.request("GET", f"/api/v1/backend-profiles/{profile_id}")
        config = dict((current or {}).get("config") or {}) if isinstance(current, dict) else {}
        if base_url:
            config["base_url"] = base_url
        else:
            config.pop("base_url", None)
        payload = dict(fields)
        payload["config"] = config
        profile = engine.request(
            "PATCH", f"/api/v1/backend-profiles/{profile_id}", json_body=payload
        )
        profile = profile if isinstance(profile, dict) else {}
    _apply_secret(
        engine, profile_id, "chat", body.get("chat_secret_action"), body.get("chat_secret")
    )
    _apply_secret(
        engine,
        profile_id,
        "embedding",
        body.get("embedding_secret_action"),
        body.get("embedding_secret"),
    )
    fresh = engine.request("GET", f"/api/v1/backend-profiles/{profile_id}")
    return public_profile(fresh if isinstance(fresh, dict) else profile)


# ------------------------------------------------------- presets/bundles


def save_preset(engine, preset_id, body: dict) -> dict:
    """Create/update a preset: the sampler form's values plus
    the carried unknown keys (verbatim) plus template_ref."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise EngineError("the preset needs a name", status=422)
    known = parse_sampler_form(body.get("sampler") or {})
    extra = body.get("extra") or {}
    if not isinstance(extra, dict):
        raise EngineError("extra preset keys must be an object", status=422)
    extra = {k: v for k, v in extra.items() if k not in SAMPLER_FIELD_BY_KEY}
    params = merge_bag(known, extra)
    payload = {
        "name": name,
        "params": params,
        "template_ref": str(body.get("template_ref") or "").strip(),
    }
    if preset_id is None:
        return engine.request("POST", "/api/v1/presets", json_body=payload)
    return engine.request("PATCH", f"/api/v1/presets/{preset_id}", json_body=payload)


def preset_view(preset: dict) -> dict:
    out = dict(preset)
    known, extra = split_bag(preset.get("params") or {})
    out["known"] = known
    out["extra"] = extra
    out["extra_names"] = sorted(extra)
    return out


def compose_bundle(stored, *, name: str, sampler_values, extra, template_ref: str) -> dict:
    """Lay the bundle form over the stored document: structural
    sections ride verbatim; name/sampler/template_ref are managed."""
    document = dict(stored or {})
    known = parse_sampler_form(sampler_values or {})
    extra = extra if isinstance(extra, dict) else {}
    extra = {k: v for k, v in extra.items() if k not in SAMPLER_FIELD_BY_KEY}
    document["name"] = name.strip()
    document["sampler"] = merge_bag(known, extra)
    ref = (template_ref or "").strip()
    if ref:
        document["template_ref"] = ref
    else:
        document.pop("template_ref", None)
    return document


def carried_sections(bundle) -> list[str]:
    names = {
        "prompt_layout": "prompt layout",
        "instruct_template": "instruct template selection",
        "context_template": "context template selection",
        "structured_output": "structured output declaration",
        "prompts": "prompt carriage",
        "prompt_order": "prompt order carriage",
        "extensions": "extension data",
    }
    return [label for key, label in names.items() if (bundle or {}).get(key)]


def bundle_view(row: dict) -> dict:
    out = dict(row)
    bundle = row.get("bundle") if isinstance(row.get("bundle"), dict) else {}
    known, extra = split_bag(bundle.get("sampler") or {})
    out["known"] = known
    out["extra"] = extra
    out["extra_names"] = sorted(extra)
    out["carried"] = carried_sections(bundle)
    return out


_SOURCE_WORDS = {
    "bundle": "the bundle",
    "character": "the character override",
    "chat": "the chat override",
    "preset": "the chat's preset",
    "default": "the engine default",
    "per-send": "a per-send choice",
}


def resolve_preview(engine, chat_id: str) -> dict:
    """What a send from this chat will use, with the SOURCE of
    every value in words. Layers, honestly kept apart:
    - the chat's preset bag (generation: engine defaults < preset
      < per-send) - each preset key's source is the preset;
    - the bundle resolution (GET /presets/resolve): bundle base
      layered under character/chat override deltas, per-key
      sources from the engine's provenance map;
    A key set by both is listed once, sourced to the preset (the
    layer generation merges last before per-send), with the
    bundle layer named in the notes."""
    chat = engine.request("GET", f"/api/v1/chats/{chat_id}")
    chat = chat if isinstance(chat, dict) else {}
    notes: list[str] = []
    rows: dict[str, dict] = {}
    preset_name = ""
    preset_id = chat.get("preset_id")
    if preset_id:
        preset = engine.request("GET", f"/api/v1/presets/{preset_id}")
        preset = preset if isinstance(preset, dict) else {}
        preset_name = str(preset.get("name") or preset_id)
        for key, value in (preset.get("params") or {}).items():
            spec = SAMPLER_FIELD_BY_KEY.get(key)
            rows[key] = {
                "key": key,
                "label": spec.label if spec else key,
                "value": value_text(value),
                "source": f"the preset '{preset_name}'",
                "source_kind": "preset",
            }
        notes.append(f"Preset applied to this chat: '{preset_name}'.")
    else:
        notes.append(
            "No preset is applied to this chat, so sampler values come from the engine "
            "defaults unless a bundle or override sets them."
        )
    view = None
    try:
        payload = engine.request("GET", "/api/v1/presets/resolve", params={"chat_id": chat_id})
        view = payload.get("effective") if isinstance(payload, dict) else None
    except EngineError as exc:
        notes.append(f"The bundle resolution could not be read ({plain_reason(exc.message)}).")
    bundle_sources: dict[str, str] = {}
    if isinstance(view, dict):
        effective = view.get("effective") or {}
        sources = view.get("sources") or {}
        sampler = effective.get("sampler") if isinstance(effective, dict) else None
        sampler_sources = sources.get("sampler") if isinstance(sources, dict) else None
        sampler_sources = sampler_sources if isinstance(sampler_sources, dict) else {}
        bundle_name = str(view.get("bundle_name") or view.get("bundle_id") or "")
        notes.append(f"Bundle in effect: '{bundle_name}'.")
        for row in view.get("applied") or []:
            if isinstance(row, dict):
                notes.append(
                    f"Applied: the {row.get('scope_kind', '?')} assignment for this chat or "
                    f"its character."
                )
        for row in view.get("shadowed") or []:
            if isinstance(row, dict):
                notes.append(
                    f"Shadowed: the {row.get('scope_kind', '?')} assignment is not used - "
                    f"{row.get('reason') or 'another assignment wins'}."
                )
        if isinstance(sampler, dict):
            for key, value in sampler.items():
                kind = str(sampler_sources.get(key, "bundle"))
                bundle_sources[key] = kind
                if key in rows:
                    continue
                spec = SAMPLER_FIELD_BY_KEY.get(key)
                words = _SOURCE_WORDS.get(kind, kind)
                if kind == "bundle" and bundle_name:
                    words = f"the bundle '{bundle_name}'"
                rows[key] = {
                    "key": key,
                    "label": spec.label if spec else key,
                    "value": value_text(value),
                    "source": words,
                    "source_kind": kind,
                }
        for key in sorted(set(rows) & set(bundle_sources)):
            if rows[key]["source_kind"] == "preset":
                notes.append(
                    f"'{key}' is set by both the preset and "
                    f"{_SOURCE_WORDS.get(bundle_sources[key], bundle_sources[key])}; a send "
                    f"uses the preset value, because per-send choices and then the preset "
                    f"layer over the engine defaults."
                )
    else:
        notes.append(
            "No bundle is assigned to this chat or its character, so no bundle values resolve."
        )
    ordered = [rows[k] for k in [f.key for f in SAMPLER_FIELDS if f.key in rows]]
    ordered += [rows[k] for k in sorted(rows) if k not in SAMPLER_FIELD_BY_KEY]
    notes.append(
        "Anything not listed comes from the engine default; a per-send choice, when one is "
        "made, wins over every layer above."
    )
    profile_id = chat.get("backend_profile_id")
    notes.append(
        f"Backend for this chat: profile {profile_id} is pinned."
        if profile_id
        else "Backend for this chat: no profile is pinned, so the engine default answers."
    )
    return {
        "chat_id": chat_id,
        "chat_title": str(chat.get("title") or ""),
        "preset_id": preset_id,
        "preset_name": preset_name,
        "rows": ordered,
        "notes": notes,
        "words": "\n".join(notes),
    }


# ------------------------------------------------------------ first-run


def first_run_status(engine) -> dict:
    """The R-04 pure rule: zero backend profiles AND zero
    characters means first run. Nothing else is inferred."""
    profiles = engine.request("GET", "/api/v1/backend-profiles")
    characters = engine.list_characters()
    count_p = len(profiles) if isinstance(profiles, list) else 0
    count_c = len(characters) if isinstance(characters, list) else 0
    return {
        "first_run": count_p == 0 and count_c == 0,
        "profile_count": count_p,
        "character_count": count_c,
    }


def connect_mind(engine, body: dict, draft_id: str = "") -> dict:
    """Step 1: create (or finish) the chosen mind's profile.

    R-05 semantics: a draft profile left by an earlier choice in
    this flow is DELETED when the finished mind is a different
    profile. The API key, when given, goes through save_profile's
    write-only tri-state and is never retained here."""
    kind = str(body.get("kind") or body.get("chat_backend") or "").strip()
    option = _OPTIONS_BY_KIND.get(kind)
    if option is None:
        raise EngineError(f"unknown mind kind: {kind or '(none)'}", status=422)
    name = str(body.get("name") or "").strip() or option.profile_name
    payload = {
        "name": name,
        "chat_backend": kind,
        "chat_model": str(body.get("chat_model") or "").strip() or option.default_model,
        "embedding_backend": str(body.get("embedding_backend") or ""),
        "embedding_model": str(body.get("embedding_model") or "").strip(),
        "base_url": str(body.get("base_url") or "").strip() or option.default_base_url,
        "stt_ref": "",
        "tts_ref": "",
    }
    key = str(body.get("api_key") or "")
    if key:
        payload["chat_secret_action"] = "set"
        payload["chat_secret"] = key
    # Reuse a same-named profile (a re-run of the flow) instead of
    # colliding with the engine's unique-name rule.
    existing_id = None
    profiles = engine.request("GET", "/api/v1/backend-profiles")
    if isinstance(profiles, list):
        for row in profiles:
            if isinstance(row, dict) and row.get("name") == name:
                existing_id = str(row.get("id") or "") or None
                break
    profile = save_profile(engine, existing_id, payload)
    if draft_id and draft_id != profile.get("id"):
        try:
            engine.request("DELETE", f"/api/v1/backend-profiles/{draft_id}")
        except EngineError:
            pass  # tidy-up only; the chosen mind stands
    return profile


def meet_someone(engine, body: dict) -> dict:
    """Step 3a: create a character from lines, or import a card
    the caller already pushed through the library import road
    (the flow's import branch resolves the newest character)."""
    from . import w02

    if str(body.get("mode") or "create") == "import":
        cid = str(body.get("character_id") or "").strip()
        if not cid:
            raise EngineError("the import did not name a character", status=422)
        rows = engine.list_characters()
        for row in rows:
            if isinstance(row, dict) and row.get("id") == cid:
                return row
        return {"id": cid, "name": str(body.get("name") or "")}
    created = w02.create_character(
        engine,
        {
            "name": str(body.get("name") or ""),
            "description": str(body.get("description") or ""),
            "personality": str(body.get("personality") or ""),
            "first_mes": str(body.get("first_mes") or body.get("first_greeting") or ""),
            "scenario": str(body.get("scenario") or ""),
            "system_prompt": str(body.get("system_prompt") or ""),
        },
    )
    return created if isinstance(created, dict) else {}


def open_greeted_chat(engine, character_id: str, profile_id: str = "") -> dict:
    """Step 3b: open the greeted chat and pin the chosen mind."""
    character = None
    for row in engine.list_characters():
        if isinstance(row, dict) and row.get("id") == character_id:
            character = row
            break
    name = str((character or {}).get("name") or "your character")
    chat = engine.create_chat(character_id=character_id, title=f"First chat with {name}")
    chat = chat if isinstance(chat, dict) else {}
    pinned = False
    if profile_id and chat.get("id"):
        try:
            updated = engine.request(
                "POST",
                f"/api/v1/chats/{chat['id']}/backend-profile",
                json_body={"profile_id": profile_id},
            )
            if isinstance(updated, dict):
                chat = updated
            pinned = chat.get("backend_profile_id") == profile_id
        except EngineError:
            pinned = False  # the greeted chat stands; pin is a refinement
    messages = engine.list_messages(str(chat.get("id") or "")) if chat.get("id") else []
    greeting = ""
    for message in messages:
        if (
            isinstance(message, dict)
            and message.get("role") == "assistant"
            and message.get("content")
        ):
            greeting = str(message["content"])
            break
    return {
        "chat": chat,
        "character": character or {"id": character_id},
        "greeting": greeting,
        "pinned": pinned,
        "message_count": len(messages),
    }


def set_user_name(engine, name: str) -> dict:
    """Step 4: the persona user-name road; empty never clears -
    an empty field keeps the current name and says so."""
    cleaned = str(name or "").strip()
    if not cleaned:
        current = engine.request("GET", "/api/v1/user-name")
        current = current if isinstance(current, dict) else {}
        return {"user_name": str(current.get("user_name") or "User"), "kept": True}
    saved = engine.request("PUT", "/api/v1/user-name", json_body={"user_name": cleaned})
    saved = saved if isinstance(saved, dict) else {}
    return {"user_name": str(saved.get("user_name") or cleaned), "kept": False}
