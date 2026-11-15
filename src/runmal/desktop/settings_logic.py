"""Settings logic (R-09): Connections & Generation, Qt-free.

The flow + field catalogue behind the two settings dialogs
(Tools → Connections…, Tools → Presets…). Everything here is
plain Python over the typed client layer, so the dialogs hold no
decisions — the same separation as R-05's wizard logic, R-06's
chat logic and R-08's character logic.

Three surfaces, all over EXISTING engine roads (no new routes):

- **Backend profiles** (R-02): list / create / edit / delete,
  write-only chat + embedding secrets (INV-023: a key travels
  once, in the secret-route body, and is never retained, shown,
  or logged — the form only ever learns stored / not stored),
  the health probe rendered as plain words (the R-05
  ``health_words``), the model list, and the per-chat pin (the
  engine has no default-profile concept: generation resolves
  explicit profile → chat pin → engine default, R-03, so the
  pin is the honest switching surface).
- **Presets** (S207): full CRUD over the open parameter bag.
  The sampler form is driven by :data:`SAMPLER_FIELDS` — the
  engine's canonical 29 bag keys as data, grouped by user task,
  every field labelled with a human name first and the technical
  key second (the studies' rule: no jargon-first naming, no flat
  settings ocean). Unknown bag keys are NOT sampler fields: the
  bag is open, and :func:`split_bag` carries them verbatim
  through every edit, exactly as the engine does.
- **Bundles, overrides, packs, resolve** (P-054): bundle CRUD
  over the validated bundle document (the shell edits the name,
  the sampler section, and the legacy template reference; the
  structural sections — prompt layout, template selections,
  structured output, prompts carriage, extensions — are carried
  verbatim and reported, never silently dropped), per-scope
  overrides with sampler deltas, pack inspect/import/export,
  and the resolve preview whose per-field sources are rendered
  as words (provenance is data, never silent).

Field ranges mirror ``runmal.backends.params.SamplingParams`` —
the values that can actually take effect at generation. Saving
is validated again by the engine (``presets.validate_params``);
its refusal words are surfaced verbatim by the dialogs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import (
    BackendProfile,
    BundleView,
    OverrideView,
    PresetDetail,
    PresetSummary,
)
from runmal.desktop.wizard_logic import health_words, plain_reason

# ------------------------------------------------------------ samplers

KIND_FLOAT = "float"
KIND_INT = "int"
KIND_STRINGS = "strings"
KIND_BIAS = "bias"


@dataclass(frozen=True)
class SamplerField:
    """One canonical sampler bag field, as form data.

    ``minimum``/``maximum`` of None mean unbounded on that side;
    ``exclusive_minimum`` marks a ``> minimum`` rule (top_p's
    ``0 < v``). Ranges mirror ``SamplingParams`` validation."""

    key: str
    label: str
    kind: str
    group: str
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False
    help: str = ""


SAMPLER_FIELDS: tuple[SamplerField, ...] = (
    # -- Core: the handful most turns are tuned with.
    SamplerField("temperature", "Temperature (creativity)", KIND_FLOAT, "Core",
                 minimum=0.0, help="Higher is wilder, lower is steadier. 0 is deterministic."),
    SamplerField("top_p", "Top P (nucleus cutoff)", KIND_FLOAT, "Core",
                 minimum=0.0, maximum=1.0, exclusive_minimum=True,
                 help="Only the smallest set of words covering this "
                      "much probability is considered."),
    SamplerField("top_k", "Top K (word shortlist)", KIND_INT, "Core",
                 minimum=0, help="Only this many top words are "
                                 "considered. 0 turns the shortlist off."),
    SamplerField("min_p", "Min P (relative floor)", KIND_FLOAT, "Core",
                 minimum=0.0, maximum=1.0,
                 help="Words below this fraction of the top word's probability are dropped."),
    # -- Penalties: repetition control.
    SamplerField("repetition_penalty", "Repetition penalty", KIND_FLOAT, "Penalties",
                 minimum=0.0, help="Above 1 discourages words already "
                                    "used; below 1 encourages them."),
    SamplerField("presence_penalty", "Presence penalty", KIND_FLOAT, "Penalties",
                 minimum=-2.0, maximum=2.0,
                 help="Positive values push toward topics not yet mentioned."),
    SamplerField("frequency_penalty", "Frequency penalty", KIND_FLOAT, "Penalties",
                 minimum=-2.0, maximum=2.0,
                 help="Positive values push against words used often, proportionally."),
    # -- Sampling filters.
    SamplerField("typical_p", "Typical P", KIND_FLOAT, "Sampling filters",
                 minimum=0.0, maximum=1.0, exclusive_minimum=True),
    SamplerField("top_a", "Top A", KIND_FLOAT, "Sampling filters",
                 minimum=0.0, maximum=1.0),
    SamplerField("tfs_z", "Tail-free sampling (TFS Z)", KIND_FLOAT, "Sampling filters",
                 minimum=0.0, maximum=1.0),
    SamplerField("epsilon_cutoff", "Epsilon cutoff", KIND_FLOAT, "Sampling filters",
                 minimum=0.0, maximum=1.0),
    SamplerField("eta_cutoff", "Eta cutoff", KIND_FLOAT, "Sampling filters",
                 minimum=0.0, maximum=1.0),
    # -- DRY: the repetition breaker with memory.
    SamplerField("dry_multiplier", "DRY multiplier", KIND_FLOAT, "DRY repetition",
                 minimum=0.0),
    SamplerField("dry_base", "DRY base", KIND_FLOAT, "DRY repetition",
                 minimum=1.0),
    SamplerField("dry_allowed_length", "DRY allowed repeat length", KIND_INT,
                 "DRY repetition", minimum=0),
    SamplerField("dry_penalty_last_n", "DRY penalty window (last N)", KIND_INT,
                 "DRY repetition", minimum=0),
    SamplerField("dry_sequence_breakers", "DRY sequence breakers", KIND_STRINGS,
                 "DRY repetition", help="One breaker per line; a breaker resets the repeat count."),
    # -- XTC: exclude-the-top-choice sampling.
    SamplerField("xtc_probability", "XTC probability", KIND_FLOAT, "XTC",
                 minimum=0.0, maximum=1.0),
    SamplerField("xtc_threshold", "XTC threshold", KIND_FLOAT, "XTC",
                 minimum=0.0, maximum=1.0),
    # -- Mirostat.
    SamplerField("mirostat_mode", "Mirostat mode", KIND_INT, "Mirostat",
                 minimum=0, maximum=2, help="0 off, 1 Mirostat, 2 Mirostat 2.0."),
    SamplerField("mirostat_tau", "Mirostat tau (target surprise)", KIND_FLOAT,
                 "Mirostat", minimum=0.0, exclusive_minimum=True),
    SamplerField("mirostat_eta", "Mirostat eta (learning rate)", KIND_FLOAT,
                 "Mirostat", minimum=0.0, exclusive_minimum=True),
    # -- Dynamic temperature.
    SamplerField("dynamic_temperature_range", "Dynamic temperature range",
                 KIND_FLOAT, "Dynamic temperature", minimum=0.0),
    SamplerField("dynamic_temperature_exponent", "Dynamic temperature exponent",
                 KIND_FLOAT, "Dynamic temperature", minimum=0.0,
                 exclusive_minimum=True),
    # -- Limits & stops.
    SamplerField("max_tokens", "Max reply tokens", KIND_INT, "Limits & stops",
                 minimum=1),
    SamplerField("context_length", "Context length", KIND_INT, "Limits & stops",
                 minimum=1),
    SamplerField("seed", "Seed", KIND_INT, "Limits & stops", minimum=0,
                 help="A fixed seed makes sampling reproducible where the backend honours it."),
    SamplerField("stop", "Stop sequences", KIND_STRINGS, "Limits & stops",
                 help="One per line; generation halts when one is produced."),
    SamplerField("logit_bias", "Logit bias (token = bias)", KIND_BIAS,
                 "Limits & stops",
                 help="One per line as 'token-id = bias', bias between -100 and 100."),
)

SAMPLER_FIELD_BY_KEY: dict[str, SamplerField] = {f.key: f for f in SAMPLER_FIELDS}

SAMPLER_GROUPS: tuple[str, ...] = tuple(
    dict.fromkeys(f.group for f in SAMPLER_FIELDS)
)


def split_bag(bag: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a preset bag into (canonical fields, extra fields).

    The bag is open: keys the sampler catalogue does not know are
    backend-specific and ride along verbatim — the editor shows
    them, carries them, and never drops them."""
    known: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in (bag or {}).items():
        if key in SAMPLER_FIELD_BY_KEY:
            known[key] = value
        else:
            extra[key] = value
    return known, extra


def merge_bag(known: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Rejoin a form's canonical values with the carried extras."""
    out = dict(extra)
    out.update(known)
    return out


def validate_bag(bag: dict[str, Any]) -> list[str]:
    """Local mirror of the engine's bag rules, as problem words.

    An empty list means the bag is well-formed. This is instant
    feedback only — the engine re-validates on save and its words
    win. Canonical fields are type/range-checked against the
    catalogue; extra fields must survive a JSON round trip."""
    problems: list[str] = []
    for key, value in (bag or {}).items():
        spec = SAMPLER_FIELD_BY_KEY.get(key)
        if spec is None:
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                problems.append(f"{key} is not a value Rúnmál can store")
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
            if not isinstance(value, list) or not all(
                isinstance(s, str) and s for s in value
            ):
                problems.append(f"{spec.label} must be a list of non-empty lines")
                continue
        elif spec.kind == KIND_BIAS:
            if not isinstance(value, dict):
                problems.append(f"{spec.label} must be token = bias lines")
                continue
            bad = False
            for raw_id, bias in value.items():
                if not isinstance(raw_id, str) or not raw_id.isdigit():
                    bad = True
                elif (
                    not isinstance(bias, (int, float))
                    or isinstance(bias, bool)
                    or not -100 <= bias <= 100
                ):
                    bad = True
            if bad:
                problems.append(
                    f"{spec.label} needs decimal token ids and biases "
                    "between -100 and 100"
                )
                continue
        if spec.kind in (KIND_INT, KIND_FLOAT):
            if spec.minimum is not None:
                if spec.exclusive_minimum and not value > spec.minimum:
                    problems.append(
                        f"{spec.label} must be above {spec.minimum:g}"
                    )
                elif not spec.exclusive_minimum and not value >= spec.minimum:
                    problems.append(
                        f"{spec.label} must be at least {spec.minimum:g}"
                    )
            if spec.maximum is not None and not value <= spec.maximum:
                problems.append(f"{spec.label} must be at most {spec.maximum:g}")
    return problems


def strings_to_text(values: Any) -> str:
    """Render a string-list bag value as one-per-line text."""
    if isinstance(values, list):
        return "\n".join(str(v) for v in values)
    return ""


def text_to_strings(text: str) -> list[str]:
    """Parse one-per-line text back to a string list."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def bias_to_text(value: Any) -> str:
    """Render a logit-bias bag value as 'token-id = bias' lines."""
    if not isinstance(value, dict):
        return ""
    lines = []
    for raw_id in sorted(value, key=lambda k: int(k) if str(k).isdigit() else 0):
        lines.append(f"{raw_id} = {value[raw_id]:g}")
    return "\n".join(lines)


def text_to_bias(text: str) -> tuple[dict[str, Any], list[str]]:
    """Parse 'token-id = bias' lines; returns (bag, problem words)."""
    out: dict[str, Any] = {}
    problems: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        raw_id, sep, raw_bias = line.partition("=")
        raw_id, raw_bias = raw_id.strip(), raw_bias.strip()
        if not sep or not raw_id.isdigit():
            problems.append(f"logit bias line {line!r} is not 'token-id = bias'")
            continue
        try:
            bias: float = float(raw_bias)
        except ValueError:
            problems.append(f"logit bias line {line!r} has no numeric bias")
            continue
        if not -100 <= bias <= 100:
            problems.append(f"logit bias for token {raw_id} is outside -100..100")
            continue
        out[raw_id] = int(bias) if bias == int(bias) else bias
    return out, problems


def value_text(value: Any) -> str:
    """One value, as display words for tables and previews."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def bag_rows(bag: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    """A bag as (field label, value words, bag key) rows — the
    canonical fields in catalogue order, extras after, labelled
    with their raw key (they have no human name)."""
    known, extra = split_bag(bag)
    rows: list[tuple[str, str, str]] = []
    for spec in SAMPLER_FIELDS:
        if spec.key in known:
            rows.append((spec.label, value_text(known[spec.key]), spec.key))
    for key in sorted(extra):
        rows.append((key, value_text(extra[key]), key))
    return rows


# -------------------------------------------------------------- profiles

CHAT_BACKEND_LABELS: dict[str, str] = {
    "fake": "Demo (canned replies, not a real model)",
    "ollama": "Ollama (on this computer)",
    "openrouter": "OpenRouter (online)",
    "aesir": "Aesir (Rúnmál's own engine, local)",
    "openai": "OpenAI-compatible (your own server)",
}

EMBEDDING_BACKEND_LABELS: dict[str, str] = {
    "": "None (no embeddings)",
    "fake": "Demo (fake embeddings)",
    "ollama": "Ollama (on this computer)",
    "aesir": "Aesir (local)",
    "openai": "OpenAI-compatible",
}


def backend_label(kind: str) -> str:
    return CHAT_BACKEND_LABELS.get(kind, kind or "—")


@dataclass(frozen=True)
class ProbeResult:
    """The Connections page's test verdict for one profile."""

    ok: bool
    words: str
    models: list[str] = field(default_factory=list)


# ------------------------------------------------------------ the flow


class SettingsFlow:
    """Driver for the R-09 dialogs, over one client.

    Holds no secret values: keys pass through :meth:`save_profile`
    as arguments, go straight to the write-only secret routes,
    and are not retained (INV-023)."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    # ------------------------------------------------------ profiles

    def list_profiles(self) -> list[BackendProfile]:
        return self._client.list_backend_profiles()

    def save_profile(
        self,
        profile_id: str | None,
        *,
        name: str,
        chat_backend: str,
        chat_model: str = "",
        embedding_backend: str = "",
        embedding_model: str = "",
        base_url: str = "",
        chat_key: str | None = None,
        embedding_key: str | None = None,
    ) -> BackendProfile:
        """Create or update one profile.

        ``base_url`` rides in the profile's config; on update the
        existing config keys are preserved (only ``base_url`` is
        managed here — an empty address removes it). Key tri-state:
        None leaves the stored key untouched, "" clears it, any
        other value stores it via the write-only route."""
        clean_name = (name or "").strip()
        if not clean_name:
            raise ClientError("the profile needs a name")
        profile: BackendProfile
        if profile_id is None:
            config = {"base_url": base_url.strip()} if base_url.strip() else None
            profile = self._client.create_backend_profile(
                clean_name,
                chat_backend,
                chat_model=chat_model.strip(),
                config=config,
            )
            if embedding_backend or embedding_model.strip():
                profile = self._client.update_backend_profile(
                    profile.id,
                    embedding_backend=embedding_backend,
                    embedding_model=embedding_model.strip(),
                )
        else:
            current = self._client.get_backend_profile(profile_id)
            config = dict(current.config or {})
            if base_url.strip():
                config["base_url"] = base_url.strip()
            else:
                config.pop("base_url", None)
            profile = self._client.update_backend_profile(
                profile_id,
                name=clean_name,
                chat_backend=chat_backend,
                chat_model=chat_model.strip(),
                embedding_backend=embedding_backend,
                embedding_model=embedding_model.strip(),
                config=config,
            )
        if chat_key is not None:
            profile = (
                self._client.set_chat_secret(profile.id, chat_key)
                if chat_key
                else self._client.clear_chat_secret(profile.id)
            )
        if embedding_key is not None:
            profile = (
                self._client.set_embedding_secret(profile.id, embedding_key)
                if embedding_key
                else self._client.clear_embedding_secret(profile.id)
            )
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        return self._client.delete_backend_profile(profile_id)

    def probe(self, profile_id: str) -> ProbeResult:
        """Health + models for one profile, as a words verdict
        (Voxta lesson: the self-test is a designed verb, and its
        result is a structured verdict, not raw JSON)."""
        profile = self._client.get_backend_profile(profile_id)
        health = self._client.profile_health(profile_id)
        models: list[dict[str, Any]] | None = None
        models_error = ""
        if health.get("ok"):
            try:
                models = self._client.profile_models(profile_id)
            except ClientError as exc:
                models_error = str(exc)
        label = f"{profile.name} — {backend_label(profile.chat_backend)}"
        names = [
            str(m.get("model_id") or m.get("display_name") or "")
            for m in (models or [])
        ]
        return ProbeResult(
            ok=bool(health.get("ok")),
            words=health_words(label, health, models, models_error),
            models=[n for n in names if n],
        )

    def profile_models(self, profile_id: str) -> list[str]:
        """Model ids a profile reports (for the model picker)."""
        return [
            str(m.get("model_id") or m.get("display_name") or "")
            for m in self._client.profile_models(profile_id)
        ]

    def pin_profile(self, chat_id: str, profile_id: str | None) -> None:
        """Pin (or unpin, with None) a profile to a chat — the
        switch the next reply obeys."""
        self._client.set_chat_backend_profile(chat_id, profile_id)

    # ------------------------------------------------------- presets

    def list_presets(self) -> list[PresetSummary]:
        return self._client.list_presets()

    def preset_detail(self, preset_id: str) -> PresetDetail:
        return self._client.get_preset_detail(preset_id)

    def save_preset(
        self,
        preset_id: str | None,
        *,
        name: str,
        params: dict[str, Any],
        template_ref: str = "",
    ) -> PresetDetail:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ClientError("the preset needs a name")
        problems = validate_bag(params)
        if problems:
            raise ClientError("preset not saved: " + "; ".join(problems))
        clean_ref = (template_ref or "").strip()
        if preset_id is None:
            return self._client.create_preset(
                clean_name, params=params, template_ref=clean_ref
            )
        return self._client.update_preset(
            preset_id,
            name=clean_name,
            params=params,
            template_ref=clean_ref,
        )

    def delete_preset(self, preset_id: str) -> bool:
        return self._client.delete_preset(preset_id)

    def duplicate_preset(self, preset_id: str) -> PresetDetail:
        detail = self._client.get_preset_detail(preset_id)
        return self._client.create_preset(
            f"{detail.name} (copy)",
            params=dict(detail.params),
            template_ref=detail.template_ref,
        )

    def apply_preset(self, chat_id: str, preset_id: str | None) -> None:
        self._client.set_chat_preset(chat_id, preset_id)

    def import_preset(
        self, payload: dict[str, Any], name: str | None = None
    ) -> PresetDetail:
        return self._client.import_preset(payload, name=name)

    def export_preset(
        self, preset_id: str, format: str | None = None
    ) -> dict[str, Any]:
        return self._client.export_preset(preset_id, format=format)

    # ------------------------------------------------------- bundles

    def list_bundles(self) -> list[BundleView]:
        return self._client.list_bundles()

    def bundle_detail(self, bundle_id: str) -> BundleView:
        return self._client.get_bundle(bundle_id)

    def save_bundle(
        self,
        bundle_id: str | None,
        *,
        name: str,
        sampler: dict[str, Any],
        template_ref: str = "",
        base: dict[str, Any] | None = None,
    ) -> BundleView:
        """Create or update one bundle document.

        The document is composed over ``base`` (the stored bundle
        when editing) so its structural sections — prompt layout,
        template selections, structured output, prompts carriage,
        extensions — are carried verbatim; this surface manages
        the name, the sampler section, and the legacy template
        reference only, and says so in the dialog."""
        clean_name = (name or "").strip()
        if not clean_name:
            raise ClientError("the bundle needs a name")
        problems = validate_bag(sampler)
        if problems:
            raise ClientError("bundle not saved: " + "; ".join(problems))
        document = dict(base or {})
        document["name"] = clean_name
        document["sampler"] = dict(sampler)
        clean_ref = (template_ref or "").strip()
        if clean_ref:
            document["template_ref"] = clean_ref
        else:
            document.pop("template_ref", None)
        if bundle_id is None:
            return self._client.create_bundle(document)
        return self._client.update_bundle(bundle_id, document)

    def delete_bundle(self, bundle_id: str) -> bool:
        return self._client.delete_bundle(bundle_id)

    def share_bundle(self, bundle_id: str) -> dict[str, Any]:
        return self._client.share_bundle(bundle_id)

    def import_bundle(
        self, payload: dict[str, Any], name: str | None = None
    ) -> BundleView:
        return self._client.import_bundle(payload, name=name)

    # ----------------------------------------------------- overrides

    def list_overrides(self) -> list[OverrideView]:
        return self._client.list_overrides()

    def set_override(
        self,
        scope_kind: str,
        owner_id: str,
        bundle_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> OverrideView:
        return self._client.set_override(
            scope_kind, owner_id, bundle_id, overrides
        )

    def delete_override(self, scope_kind: str, owner_id: str) -> bool:
        return self._client.delete_override(scope_kind, owner_id)

    # ---------------------------------------------------------- packs

    def inspect_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.inspect_pack(payload)

    def import_pack(
        self, payload: dict[str, Any], on_conflict: str = "create_new"
    ) -> dict[str, Any]:
        return self._client.import_pack(payload, on_conflict=on_conflict)

    def export_pack(
        self,
        name: str,
        bundle_ids: list[str] | None = None,
        preset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._client.export_pack(
            name, bundle_ids=bundle_ids, preset_ids=preset_ids
        )

    # -------------------------------------------------------- resolve

    def resolve(
        self,
        chat_id: str | None = None,
        character_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self._client.resolve_presets(
            chat_id=chat_id, character_id=character_id
        )


# ------------------------------------------------------------ resolve words


def carried_sections(bundle: dict[str, Any] | None) -> list[str]:
    """The structural sections a bundle document carries, named —
    so the editor can say what it preserves without editing it."""
    names = {
        "prompt_layout": "prompt layout",
        "instruct_template": "instruct template selection",
        "context_template": "context template selection",
        "structured_output": "structured output declaration",
        "prompts": "prompt carriage",
        "prompt_order": "prompt order carriage",
        "extensions": "extension data",
    }
    out = []
    for key, label in names.items():
        value = (bundle or {}).get(key)
        if value:
            out.append(label)
    return out


def effective_rows(
    view: dict[str, Any] | None,
) -> list[tuple[str, str, str]]:
    """The resolve view's effective sampler as preview rows:
    (field label, value words, source words). Sources come from
    the view's provenance map — 'bundle', 'character', 'chat'."""
    if not view:
        return []
    effective = view.get("effective")
    sources = view.get("sources")
    sampler = effective.get("sampler") if isinstance(effective, dict) else None
    sampler_sources = sources.get("sampler") if isinstance(sources, dict) else None
    if not isinstance(sampler, dict):
        return []
    if not isinstance(sampler_sources, dict):
        sampler_sources = {}
    rows: list[tuple[str, str, str]] = []
    known, extra = split_bag(sampler)
    for spec in SAMPLER_FIELDS:
        if spec.key in known:
            rows.append(
                (
                    spec.label,
                    value_text(known[spec.key]),
                    str(sampler_sources.get(spec.key, "bundle")),
                )
            )
    for key in sorted(extra):
        rows.append(
            (key, value_text(extra[key]), str(sampler_sources.get(key, "bundle")))
        )
    return rows


def resolve_notes(view: dict[str, Any] | None) -> list[str]:
    """The resolve view in plain words: which bundle, which
    assignments applied, and anything shadowed — never silent."""
    if not view:
        return ["No bundle is assigned to this target, so no bundle resolves."]
    notes = [f"Bundle: {view.get('bundle_name') or view.get('bundle_id') or '—'}"]
    for row in view.get("applied") or []:
        if isinstance(row, dict):
            notes.append(
                f"Applied: the {row.get('scope_kind', '?')} assignment "
                f"({row.get('owner_id', '?')})"
            )
    for row in view.get("shadowed") or []:
        if isinstance(row, dict):
            notes.append(
                f"Shadowed: the {row.get('scope_kind', '?')} assignment "
                f"is not used — {row.get('reason') or 'another assignment wins'}"
            )
    effective = view.get("effective")
    if isinstance(effective, dict):
        for section in (
            "prompt_layout", "instruct_template", "context_template",
            "structured_output", "template_ref",
        ):
            if effective.get(section):
                notes.append(f"Also in effect: {section.replace('_', ' ')}")
    return notes


__all__ = [
    "CHAT_BACKEND_LABELS",
    "EMBEDDING_BACKEND_LABELS",
    "KIND_BIAS",
    "KIND_FLOAT",
    "KIND_INT",
    "KIND_STRINGS",
    "SAMPLER_FIELDS",
    "SAMPLER_FIELD_BY_KEY",
    "SAMPLER_GROUPS",
    "ProbeResult",
    "SamplerField",
    "SettingsFlow",
    "backend_label",
    "bag_rows",
    "bias_to_text",
    "carried_sections",
    "effective_rows",
    "merge_bag",
    "plain_reason",
    "resolve_notes",
    "split_bag",
    "strings_to_text",
    "text_to_bias",
    "text_to_strings",
    "validate_bag",
    "value_text",
]
