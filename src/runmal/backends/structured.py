"""Structured output: grammar/JSON-mode as declared data (P-061).

Roadmap line: *Grammar/JSON-mode where backends offer it, as a
prompt citizen (structured replies for bridges/games).*

Until P-061 the tree had exactly one trace of this feature:
``Capabilities.structured_output`` -- a flag no adapter set True,
while no chat adapter sent any grammar or JSON field on any wire.
A preset could not ask for a structured reply, the inspector
could not show one, and nothing distinguished "the backend
enforces this shape" from "we hope and parse later".

This module makes the mode DATA, beside the sampler truth: no
DB, no I/O, no HTTP. It owns four things and nothing else: the
structured-output declaration as data, the per-backend truth
about which modes are honestly served, the wire payload builders
that turn a declaration into payload fields, and a client-side
validation companion for replies. Adapters, the prompt service,
and preset bundles consume it; it imports no adapter at module
level (adapter agreement is enforced by the audit + battery),
so there is no import cycle.

Wire truth, proven from Rúnmál's own adapters (P-061 scout):
the OpenAI-shaped ``POST /chat/completions`` wire carries
``response_format`` (``json_object`` / ``json_schema``) -- the
public shape both the ``openai`` and ``openrouter`` adapters
speak; Ollama's ``POST /api/chat`` carries a top-level
``format`` field (``"json"`` or a JSON schema object). Aesir's
P-009 route matrix never recorded ``response_format``, so Aesir
declares nothing. The fake backend emits scripted text and can
enforce nothing. NO wire in this tree carries a GBNF grammar
field, so ``grammar`` is greyed on every current backend with
reason ``grammar_not_on_wire`` -- a first-class declared mode,
honestly unserved until an adapter declares it, never faked.

:func:`validate_reply` is a VALIDATION companion: it checks a
finished reply on the client side and is labelled validation
everywhere. It never claims the backend enforced anything, it
never repairs a reply, and a schema using constraints outside
its documented subset is ``not_validatable``, never ``ok``.

No migration: a declaration is per-request / per-preset data
(the P-049 / P-058 precedent). Migration head stays 0035; the
provisional 0036 eyed by both P-060 and this slice was taken
by NEITHER. No row claims ``measured``: nothing here probes a
live server; provenance is ``declared`` (this tree's wire) or
``ledger`` (the P-009 matrix) only.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from runmal.backends.models import ModelInfo

__all__ = [
    "MODE_OFF",
    "MODE_JSON_OBJECT",
    "MODE_JSON_SCHEMA",
    "MODE_GRAMMAR",
    "MODES",
    "AVAILABLE",
    "GREYED",
    "SOURCE_DECLARED",
    "SOURCE_LEDGER",
    "REASON_SUPPORTED",
    "REASON_NOT_DECLARED",
    "REASON_ROUTE_NOT_SERVED",
    "REASON_GRAMMAR_NOT_ON_WIRE",
    "STRUCTURED_WIRE",
    "StructuredOutput",
    "StructuredTruth",
    "structured_from_data",
    "structured_to_data",
    "truth_for_model",
    "truth_for_backend",
    "structured_matrix",
    "audit_structured_truth",
    "wire_payload",
    "plan_structured",
    "ReplyValidation",
    "validate_reply",
]

MODE_OFF = "off"
MODE_JSON_OBJECT = "json_object"
MODE_JSON_SCHEMA = "json_schema"
MODE_GRAMMAR = "grammar"
MODES = (MODE_OFF, MODE_JSON_OBJECT, MODE_JSON_SCHEMA, MODE_GRAMMAR)

AVAILABLE = "available"
GREYED = "greyed"
SOURCE_DECLARED = "declared"
SOURCE_LEDGER = "ledger"
REASON_SUPPORTED = "supported"
REASON_NOT_DECLARED = "not_declared"
REASON_ROUTE_NOT_SERVED = "route_not_served"
REASON_GRAMMAR_NOT_ON_WIRE = "grammar_not_on_wire"

_DATA_KEYS = frozenset({"mode", "schema", "grammar", "name", "strict"})
_MODE_KEYS = {
    MODE_OFF: frozenset({"mode"}),
    MODE_JSON_OBJECT: frozenset({"mode"}),
    MODE_JSON_SCHEMA: frozenset({"mode", "schema", "name", "strict"}),
    MODE_GRAMMAR: frozenset({"mode", "grammar"}),
}
_KNOWN_BACKENDS = frozenset({"openai", "openrouter", "ollama", "aesir", "fake"})
_JSON_BACKENDS = frozenset({"openai", "openrouter", "ollama"})


@dataclass(frozen=True)
class StructuredOutput:
    """One declared structured-output mode, as validated data.

    ``schema`` is carried only by ``json_schema`` (a JSON Schema
    object); ``grammar`` only by ``grammar`` (the grammar text,
    carried as data, never parsed here); ``name`` / ``strict``
    qualify ``json_schema``. The default instance is inactive.
    """

    mode: str = MODE_OFF
    schema: dict | None = None
    grammar: str | None = None
    name: str = "response"
    strict: bool = False

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"unknown structured mode: {self.mode!r}")
        if not isinstance(self.strict, bool):
            raise ValueError("structured 'strict' must be a boolean")
        if self.mode in (MODE_OFF, MODE_JSON_OBJECT):
            if self.schema is not None or self.grammar is not None:
                raise ValueError(
                    f"mode {self.mode!r} carries neither schema nor grammar"
                )
        elif self.mode == MODE_JSON_SCHEMA:
            if not isinstance(self.schema, dict):
                raise ValueError("mode 'json_schema' requires a schema object")
            if self.grammar is not None:
                raise ValueError("mode 'json_schema' carries no grammar")
            if not isinstance(self.name, str) or not self.name:
                raise ValueError("json_schema 'name' must be a non-empty string")
            try:
                json.dumps(self.schema)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "structured schema is not JSON-serializable"
                ) from exc
        elif self.mode == MODE_GRAMMAR:
            if not isinstance(self.grammar, str) or not self.grammar.strip():
                raise ValueError("mode 'grammar' requires a non-empty grammar text")
            if self.schema is not None:
                raise ValueError("mode 'grammar' carries no schema")

    def is_active(self) -> bool:
        """True when a servable mode is declared (not ``off``)."""
        return self.mode != MODE_OFF

    def to_dict(self) -> dict:
        return structured_to_data(self)


def structured_from_data(data: object) -> StructuredOutput:
    """Validate untrusted data into a :class:`StructuredOutput`.

    The strict boundary, in the ``policy_from_data`` /
    ``layout_from_data`` style: a malformed declaration is
    refused with ValueError, never repaired silently and never
    partially applied. ``data`` must be a dict and ``mode``
    must be present. A field that does not belong to the
    declared mode raises if the key is PRESENT at all, even
    as ``None``.
    """
    if not isinstance(data, dict):
        raise ValueError("structured output declaration must be an object")
    unknown = set(data) - _DATA_KEYS
    if unknown:
        raise ValueError(f"unknown structured output keys: {sorted(unknown)}")
    if "mode" not in data:
        raise ValueError("structured output declaration requires 'mode'")
    mode = data["mode"]
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError(f"unknown structured mode: {mode!r}")
    extra = set(data) - _MODE_KEYS[mode]
    if extra:
        raise ValueError(
            f"structured mode {mode!r} does not carry field(s): {sorted(extra)}"
        )
    schema = data.get("schema")
    if schema is not None:
        if not isinstance(schema, dict):
            raise ValueError("structured 'schema' must be an object")
        schema = copy.deepcopy(schema)
    name = data.get("name", "response")
    if mode == MODE_JSON_SCHEMA and (not isinstance(name, str) or not name):
        raise ValueError("structured 'name' must be a non-empty string")
    return StructuredOutput(
        mode=mode,
        schema=schema,
        grammar=data.get("grammar"),
        name=name,
        strict=data.get("strict", False),
    )


def structured_to_data(structured: StructuredOutput) -> dict:
    """The canonical data form; a fixed point of from_data.

    Serialised forms are deep copies -- mutating a returned
    dict never corrupts the frozen declaration's schema.
    """
    out: dict = {"mode": structured.mode}
    if structured.mode == MODE_JSON_SCHEMA:
        out["schema"] = copy.deepcopy(structured.schema)
        out["name"] = structured.name
        out["strict"] = structured.strict
    elif structured.mode == MODE_GRAMMAR:
        out["grammar"] = structured.grammar
    return out


# ---------------- per-backend truth ----------------

#: backend_key -> {mode: wire field} for served modes only.
#: It is a declaration, never copied payload code; the audit
#: and the battery hold it against the adapters.
STRUCTURED_WIRE: dict[str, dict[str, str]] = {
    "openai": {
        MODE_JSON_OBJECT: "response_format",
        MODE_JSON_SCHEMA: "response_format",
    },
    "openrouter": {
        MODE_JSON_OBJECT: "response_format",
        MODE_JSON_SCHEMA: "response_format",
    },
    "ollama": {
        MODE_JSON_OBJECT: "format",
        MODE_JSON_SCHEMA: "format",
    },
}


@dataclass(frozen=True)
class StructuredTruth:
    """One mode's truth for one backend+model, as data."""

    mode: str
    state: str
    supported: bool
    reason_code: str
    reason: str
    source: str
    backend_key: str
    model_id: str
    wire_field: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "state": self.state,
            "supported": self.supported,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "source": self.source,
            "backend_key": self.backend_key,
            "model_id": self.model_id,
            "wire_field": self.wire_field,
        }


def _row(model: ModelInfo, mode: str, state: str, code: str, reason: str,
         source: str, wire_field: str | None) -> StructuredTruth:
    return StructuredTruth(
        mode=mode, state=state, supported=state == AVAILABLE,
        reason_code=code, reason=reason, source=source,
        backend_key=model.backend_key, model_id=model.model_id,
        wire_field=wire_field,
    )


def truth_for_model(model: ModelInfo) -> list[StructuredTruth]:
    """Truth rows, one per mode in MODES order, for one model.

    Judged by ``model.backend_key``; an unknown backend raises
    ValueError (the ``capabilities.default_model`` discipline).
    """
    backend_key = model.backend_key
    if backend_key not in _KNOWN_BACKENDS:
        raise ValueError(f"unknown backend: {backend_key!r}")
    rows = [_row(model, MODE_OFF, AVAILABLE, REASON_SUPPORTED, "",
                 SOURCE_DECLARED, None)]
    served = STRUCTURED_WIRE.get(backend_key, {})
    for mode in (MODE_JSON_OBJECT, MODE_JSON_SCHEMA):
        wire_field = served.get(mode)
        if wire_field is not None:
            rows.append(_row(model, mode, AVAILABLE, REASON_SUPPORTED, "",
                             SOURCE_DECLARED, wire_field))
        elif backend_key == "aesir":
            rows.append(_row(
                model, mode, GREYED, REASON_ROUTE_NOT_SERVED,
                "Aesir's route does not serve structured output: the "
                "P-009 route matrix never recorded response_format, and "
                "map_params maps only the P-009 sampler subset",
                SOURCE_LEDGER, None))
        else:  # fake
            rows.append(_row(
                model, mode, GREYED, REASON_NOT_DECLARED,
                "the fake backend emits scripted text; scripted text "
                "cannot enforce a structured mode, so the fake does "
                "not declare one",
                SOURCE_DECLARED, None))
    grammar_source = SOURCE_LEDGER if backend_key == "aesir" else SOURCE_DECLARED
    rows.append(_row(
        model, MODE_GRAMMAR, GREYED, REASON_GRAMMAR_NOT_ON_WIRE,
        "no adapter wire in this tree carries a grammar field; the "
        "grammar mode is declared data until an adapter serves it",
        grammar_source, None))
    return rows


def truth_for_backend(backend_key: str) -> list[StructuredTruth]:
    """Truth rows for the named backend's default model."""
    from runmal.backends.capabilities import default_model

    return truth_for_model(default_model(backend_key))


def _backend_dict(backend_key: str) -> dict:
    from runmal.backends.capabilities import default_model

    model = default_model(backend_key)
    rows = truth_for_model(model)
    return {
        "backend_key": backend_key,
        "model_id": model.model_id,
        "modes": [r.to_dict() for r in rows],
        "available": [r.mode for r in rows if r.state == AVAILABLE],
        "greyed": [r.mode for r in rows if r.state == GREYED],
    }


def structured_matrix() -> dict:
    """Structured truth for every chat backend, registry order."""
    from runmal.backends.profiles import CHAT_BACKENDS

    return {
        "backends": [_backend_dict(key) for key in CHAT_BACKENDS],
        "audit": audit_structured_truth(),
    }


# ---------------- wire builders ----------------

def wire_payload(backend_key: str, structured: StructuredOutput | None) -> dict:
    """The payload fields for one declaration on one backend.

    Inactive (``off`` / ``None``): ``{}`` for every known
    backend -- byte-identical payloads to pre-P-061. An ACTIVE
    mode the backend does not serve raises ValueError; the
    builder never degrades a mode, substitutes another, or
    emits a partial field. An unknown backend raises.
    """
    if backend_key not in _KNOWN_BACKENDS:
        raise ValueError(f"unknown backend: {backend_key!r}")
    if structured is None or not structured.is_active():
        return {}
    wire_field = STRUCTURED_WIRE.get(backend_key, {}).get(structured.mode)
    if wire_field is None:
        raise ValueError(
            f"backend {backend_key!r} does not serve structured "
            f"mode {structured.mode!r}"
        )
    if backend_key in ("openai", "openrouter"):
        if structured.mode == MODE_JSON_OBJECT:
            return {"response_format": {"type": "json_object"}}
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": structured.name,
                    "schema": copy.deepcopy(structured.schema),
                    "strict": structured.strict,
                },
            }
        }
    # ollama: the format field lives top-level on /api/chat.
    if structured.mode == MODE_JSON_OBJECT:
        return {"format": "json"}
    return {"format": copy.deepcopy(structured.schema)}


# ---------------- audit ----------------

def audit_structured_truth() -> list[str]:
    """Drift findings across the structured truth sources.

    ``[]`` = agreement; findings are data, never hidden.
    (a) truth rows agree with STRUCTURED_WIRE; (b) wire_payload
    agrees with the declaration; (c) each backend's default-model
    ``Capabilities.structured_output`` flag is True exactly when
    the backend serves at least one JSON mode; (d) grammar is
    greyed for every backend in CHAT_BACKENDS.
    """
    from runmal.backends.capabilities import default_model
    from runmal.backends.profiles import CHAT_BACKENDS

    findings: list[str] = []
    samples = {
        MODE_JSON_OBJECT: StructuredOutput(mode=MODE_JSON_OBJECT),
        MODE_JSON_SCHEMA: StructuredOutput(
            mode=MODE_JSON_SCHEMA, schema={"type": "object"}),
        MODE_GRAMMAR: StructuredOutput(
            mode=MODE_GRAMMAR, grammar='root ::= "x"'),
    }
    for backend_key in CHAT_BACKENDS:
        model = default_model(backend_key)
        rows = truth_for_model(model)
        declared = STRUCTURED_WIRE.get(backend_key, {})
        for row in rows:
            if row.mode == MODE_OFF:
                if row.state != AVAILABLE or row.wire_field is not None:
                    findings.append(
                        f"{backend_key}: off row is not plainly available")
                continue
            if row.state == AVAILABLE:
                if declared.get(row.mode) != row.wire_field:
                    findings.append(
                        f"{backend_key}/{row.mode}: available row wire_field "
                        f"{row.wire_field!r} != STRUCTURED_WIRE "
                        f"{declared.get(row.mode)!r}")
            elif row.mode in declared:
                findings.append(
                    f"{backend_key}/{row.mode}: greyed mode present in "
                    f"STRUCTURED_WIRE")
            # (b) builder agreement for this row
            sample = samples[row.mode]
            if row.state == AVAILABLE:
                try:
                    payload = wire_payload(backend_key, sample)
                except ValueError:
                    findings.append(
                        f"{backend_key}/{row.mode}: wire_payload refuses a "
                        f"served mode")
                else:
                    if set(payload) != {row.wire_field}:
                        findings.append(
                            f"{backend_key}/{row.mode}: wire_payload keys "
                            f"{sorted(payload)} != [{row.wire_field!r}]")
            else:
                try:
                    wire_payload(backend_key, sample)
                except ValueError:
                    pass
                else:
                    findings.append(
                        f"{backend_key}/{row.mode}: wire_payload builds a "
                        f"field for an unserved mode")
            # (d) grammar greyed everywhere
            if row.mode == MODE_GRAMMAR and row.state != GREYED:
                findings.append(f"{backend_key}: grammar is not greyed")
        # (c) capability flag == serves at least one JSON mode
        serves_json = any(
            r.state == AVAILABLE and r.mode in (MODE_JSON_OBJECT, MODE_JSON_SCHEMA)
            for r in rows
        )
        if model.capabilities.structured_output != serves_json:
            findings.append(
                f"{backend_key}: structured_output flag "
                f"{model.capabilities.structured_output} != truth {serves_json}")
    return findings


# ---------------- planner (clamp precedent) ----------------

def plan_structured(
    structured: StructuredOutput | None, model: ModelInfo
) -> tuple[StructuredOutput | None, list[str]]:
    """Degrade an unserved declaration with a warning, never silently.

    The ``negotiation.clamp_params`` shape: ``None`` / inactive
    plans to ``(None, [])``; an active served mode passes
    through as the same object with no warnings; an active
    unserved mode degrades to ``None`` with exactly one warning
    whose text carries the truth row's reason code.
    """
    if structured is None or not structured.is_active():
        return None, []
    for row in truth_for_model(model):
        if row.mode == structured.mode:
            if row.state == AVAILABLE:
                return structured, []
            warning = (
                f"structured_output dropped: mode {structured.mode!r} is "
                f"not served by backend {model.backend_key!r} for model "
                f"{model.model_id!r} ({row.reason_code})"
            )
            return None, [warning]
    raise AssertionError("declared mode missing from truth rows")


# ---------------- validation companion ----------------

@dataclass(frozen=True)
class ReplyValidation:
    """Client-side validation of one reply: never enforcement."""

    status: str  # "ok" | "invalid" | "not_validatable"
    errors: tuple[str, ...] = ()
    parsed: object = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "parsed": self.parsed,
        }


_ANNOTATION_KEYS = frozenset({"$schema", "title", "description"})
_SUBSET_KEYS = frozenset(
    {"type", "required", "properties", "items", "enum"}
) | _ANNOTATION_KEYS
_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _find_unsupported(schema: object) -> str | None:
    """First out-of-subset constraining keyword in a schema, if any."""
    if not isinstance(schema, dict):
        return "schema is not an object"
    for key in schema:
        if key not in _SUBSET_KEYS:
            return key
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for subschema in properties.values():
            found = _find_unsupported(subschema)
            if found is not None:
                return found
    items = schema.get("items")
    if isinstance(items, dict):
        return _find_unsupported(items)
    return None


def _validate_value(value: object, schema: dict, path: str,
                    errors: list[str]) -> None:
    type_name = schema.get("type")
    if type_name is not None:
        check = _TYPE_CHECKS.get(type_name) if isinstance(type_name, str) else None
        if check is None:
            errors.append(f"{path}: unsupported schema type {type_name!r}")
            return
        if not check(value):
            errors.append(f"{path}: expected {type_name}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value not in enum")
    if isinstance(value, dict):
        for name in schema.get("required") or []:
            if name not in value:
                errors.append(f"{path}.{name}: required but missing")
        properties = schema.get("properties") or {}
        for key, subschema in properties.items():
            if key in value and isinstance(subschema, dict):
                _validate_value(value[key], subschema, f"{path}.{key}", errors)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], f"{path}[{index}]", errors)


def validate_reply(text: str, structured: StructuredOutput | None) -> ReplyValidation:
    """Check a finished reply against the declared JSON mode.

    Client-side VALIDATION, never enforcement: it runs after
    the fact, in this process. No repair is attempted -- code
    fences are not stripped, trailing commas are not fixed.
    """
    if structured is None or not structured.is_active():
        return ReplyValidation(status="not_validatable")
    if structured.mode == MODE_GRAMMAR:
        return ReplyValidation(
            status="not_validatable",
            errors=(
                "grammar replies cannot be validated: no GBNF parser "
                "ships in this tree",
            ),
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return ReplyValidation(
            status="invalid",
            errors=(
                f"reply is not valid JSON: {exc.msg} "
                f"(line {exc.lineno} column {exc.colno})",
            ),
        )
    if structured.mode == MODE_JSON_OBJECT:
        if not isinstance(parsed, dict):
            return ReplyValidation(
                status="invalid",
                errors=("reply is not a JSON object",),
                parsed=parsed,
            )
        return ReplyValidation(status="ok", parsed=parsed)
    # json_schema: the documented subset validator.
    unsupported = _find_unsupported(structured.schema)
    if unsupported is not None:
        return ReplyValidation(
            status="not_validatable",
            errors=(
                f"schema uses keyword {unsupported!r} outside the "
                f"validated subset; the reply is not validated "
                f"against it",
            ),
            parsed=parsed,
        )
    errors: list[str] = []
    _validate_value(parsed, structured.schema or {}, "$", errors)
    if errors:
        return ReplyValidation(
            status="invalid", errors=tuple(errors), parsed=parsed)
    return ReplyValidation(status="ok", parsed=parsed)
