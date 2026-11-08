"""Plugin settings UI (P-098): generated from declared schemas.

Roadmap line: "Plugin settings UI generated from declared
schemas." Design: hidden_files/P098_DESIGN.md; survey:
hidden_files/P098_SCOUT.md.

P-081 stores a plugin's settings block {schema, defaults}
verbatim and leaves interpreting the schema to this slice.
One generic renderer does it for every plugin: the schema
is DATA, and the form, the HTML and the validation all
derive from that data alone. No hand-built form exists
for any plugin, and a plugin whose declaration carries
no fields (empty schema, or settings=None) gets an honest
no-settings surface, never an empty broken form.

Validation is strict - the mirror image of the citizens'
lenient config_from_manifest roads. A value the declared
schema does not accept is refused with NAMED errors
(every bad field, every code), never silently coerced,
clamped or dropped. A broken declaration itself (unknown
type, unknown spec key, inverted bounds, an invalid
declared default) raises SettingsSchemaError naming the
field: the author's defect, loud at render time.

Persistence is the declared road of this slice, shaped by
the P-094 custody rules: owner values live ONLY in the
P-089 file-idiom store data_dir()/plugin_settings/<uid>
.json (validated complete effective values, re-validated
on every read), export as one checksummed document, and
delete per plugin - a plugin's settings leave with the
plugin; no hostage state, no side-channel store. Shipped
citizens keep reading their manifest defaults at runtime
in this slice; the store is the road their owner values
travel, stated plainly in the slice doc.

Wiring: register_plugin only. build_registry / create_app
are unchanged. No migration: head stays 0041. Sandbox
stance (P-082): only v1 surface permissions are declared,
so the derived grant set is EMPTY. Deterministic, local,
no network. See docs/PLUGIN_SETTINGS_UI_2026-11-07.md.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.plugin-settings-ui"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "plugin-settings-panel"
FORM_FORMAT = "runmal-plugin-settings-form"
FORM_VERSION = 1
EXPORT_FORMAT = "runmal-plugin-settings-export"
EXPORT_VERSION = 1
STORE_SCHEMA = "runmal-p098-plugin-settings-v1"
STORE_DIR_NAME = "plugin_settings"
FIELD_TYPES = frozenset({"string", "integer", "number", "boolean"})
_SPEC_KEYS = frozenset({
    "type", "minimum", "maximum", "minLength", "maxLength",
    "min_length", "max_length", "enum", "default", "title",
    "label", "description", "help", "required"})
_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
MAX_FIELDS = 64
MAX_ENUM_VALUES = 64
MAX_TEXT_CHARS = 4000


class SettingsError(ValueError):
    """A settings refusal (house 422)."""


class SettingsSchemaError(SettingsError):
    """The declared schema itself is outside the contract."""


class SettingsStoreError(SettingsError):
    """The settings store is corrupt or holds values the
    current declared schema no longer accepts."""


class SettingsValidationError(SettingsError):
    """Submitted values refused: carries every named error."""

    def __init__(self, errors: list[dict]):
        self.errors = [dict(row) for row in errors]
        summary = "; ".join(
            row["field"] + ": " + row["message"] for row in self.errors)
        super().__init__("settings refused: " + summary)

    def to_dict(self) -> dict:
        return {"errors": [dict(row) for row in self.errors]}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _checksum(payload) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def settings_block(manifest) -> dict | None:
    """The manifest's settings block, or None (both shapes:
    a PluginManifest and a plain manifest dict are accepted,
    the config_from_manifest pattern)."""
    settings = (manifest.get("settings") if isinstance(manifest, dict)
                else getattr(manifest, "settings", None))
    if settings is None:
        return None
    if not isinstance(settings, dict):
        raise SettingsSchemaError("settings must be an object")
    return settings


def declared_schema(manifest) -> dict:
    block = settings_block(manifest)
    if block is None:
        return {}
    schema = block.get("schema", {})
    if not isinstance(schema, dict):
        raise SettingsSchemaError("settings.schema must be an object")
    return schema


def declared_defaults(manifest) -> dict:
    block = settings_block(manifest)
    if block is None:
        return {}
    defaults = block.get("defaults", {})
    if not isinstance(defaults, dict):
        raise SettingsSchemaError("settings.defaults must be an object")
    return dict(defaults)


@dataclass(frozen=True)
class FieldSpec:
    """One declared field, interpreted (design section 1)."""

    name: str
    type: str
    label: str
    help: str = ""
    required: bool = False
    has_default: bool = False
    default: object = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum: tuple | None = None

    @property
    def widget(self) -> str:
        if self.enum is not None:
            return "select"
        if self.type == "boolean":
            return "checkbox"
        if self.type in ("integer", "number"):
            return "number"
        return "text"

    def constraints(self) -> dict:
        return {"minimum": self.minimum, "maximum": self.maximum,
                "min_length": self.min_length,
                "max_length": self.max_length,
                "enum": (list(self.enum) if self.enum is not None else None)}

    def to_dict(self, value) -> dict:
        return {"name": self.name, "type": self.type,
                "widget": self.widget, "label": self.label,
                "help": self.help, "required": self.required,
                "default": copy.deepcopy(self.default) if self.has_default else None,
                "has_default": self.has_default,
                "value": copy.deepcopy(value),
                "constraints": self.constraints()}


def _human_label(name: str) -> str:
    text = name.replace("_", " ").replace("-", " ").replace(".", " ")
    text = " ".join(text.split())
    return text[:1].upper() + text[1:] if text else name


def _check_enum(name: str, raw, field_type: str) -> tuple:
    if not isinstance(raw, list) or not raw:
        raise SettingsSchemaError(
            "field " + repr(name) + ": enum must be a non-empty list")
    if len(raw) > MAX_ENUM_VALUES:
        raise SettingsSchemaError(
            "field " + repr(name) + ": enum exceeds "
            + str(MAX_ENUM_VALUES) + " values")
    for item in raw:
        _check_value_type(name, field_type, item, schema=True)
    if len(set(json.dumps(v, sort_keys=True) for v in raw)) != len(raw):
        raise SettingsSchemaError(
            "field " + repr(name) + ": enum has duplicate values")
    return tuple(raw)


def _check_value_type(name: str, field_type: str, value, *, schema: bool) -> None:
    """Type gate for DECLARATION-side values (enum members,
    via _check_enum). Raises SettingsSchemaError naming the
    field; submitted owner values are judged separately by
    _validate_field, which returns named errors instead."""
    ok = True
    if field_type == "string":
        ok = isinstance(value, str)
    elif field_type == "integer":
        ok = _is_int(value)
    elif field_type == "number":
        ok = _is_number(value) and math.isfinite(float(value))
    elif field_type == "boolean":
        ok = isinstance(value, bool)
    if not ok:
        raise SettingsSchemaError(
            "field " + repr(name) + ": value " + repr(value)
            + " is not of declared type " + repr(field_type))


def _bound(name: str, spec: dict, key: str, field_type: str):
    value = spec.get(key)
    if value is None:
        return None
    if field_type not in ("integer", "number"):
        raise SettingsSchemaError(
            "field " + repr(name) + ": " + key
            + " applies only to numeric fields")
    if not _is_number(value) or not math.isfinite(float(value)):
        raise SettingsSchemaError(
            "field " + repr(name) + ": " + key + " must be a finite number")
    if field_type == "integer" and not _is_int(value):
        raise SettingsSchemaError(
            "field " + repr(name) + ": " + key
            + " must be an integer for an integer field")
    return value


def _length_bound(name: str, spec: dict, keys: tuple, field_type: str):
    value = None
    for key in keys:
        if key in spec:
            value = spec.get(key)
    if value is None:
        return None
    if field_type != "string":
        raise SettingsSchemaError(
            "field " + repr(name) + ": length bounds apply "
            "only to string fields")
    if not _is_int(value) or value < 0:
        raise SettingsSchemaError(
            "field " + repr(name) + ": length bound must be "
            "a non-negative integer")
    return value


def parse_settings_schema(manifest) -> tuple[FieldSpec, ...]:
    """Interpret the declared schema (design section 1).
    Field order is declaration order. A defaults entry with
    no schema field is a declaration defect and raises."""
    schema = declared_schema(manifest)
    defaults = declared_defaults(manifest)
    if len(schema) > MAX_FIELDS:
        raise SettingsSchemaError(
            "settings schema exceeds " + str(MAX_FIELDS) + " fields")
    specs: list[FieldSpec] = []
    for name, raw in schema.items():
        specs.append(_parse_field(name, raw, defaults))
    known = {spec.name for spec in specs}
    for key in defaults:
        if key not in known:
            raise SettingsSchemaError(
                "settings.defaults names undeclared field " + repr(key))
    return tuple(specs)


def _parse_field(name, raw, defaults: dict) -> FieldSpec:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise SettingsSchemaError("invalid settings field name: " + repr(name))
    if not isinstance(raw, dict):
        raise SettingsSchemaError(
            "field " + repr(name) + ": declaration must be an object")
    unknown = set(raw) - _SPEC_KEYS
    if unknown:
        raise SettingsSchemaError(
            "field " + repr(name) + ": unknown declaration keys: "
            + repr(sorted(unknown, key=repr)))
    field_type = raw.get("type")
    if field_type not in FIELD_TYPES:
        raise SettingsSchemaError(
            "field " + repr(name) + ": unknown or missing type "
            + repr(field_type))
    minimum = _bound(name, raw, "minimum", field_type)
    maximum = _bound(name, raw, "maximum", field_type)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise SettingsSchemaError(
            "field " + repr(name) + ": minimum exceeds maximum")
    min_length = _length_bound(name, raw, ("minLength", "min_length"), field_type)
    max_length = _length_bound(name, raw, ("maxLength", "max_length"), field_type)
    if min_length is not None and max_length is not None and min_length > max_length:
        raise SettingsSchemaError(
            "field " + repr(name) + ": minLength exceeds maxLength")
    enum = None
    if "enum" in raw and raw.get("enum") is not None:
        enum = _check_enum(name, raw.get("enum"), field_type)
    label = raw.get("title") or raw.get("label") or _human_label(name)
    if not isinstance(label, str) or not 1 <= len(label) <= 120:
        raise SettingsSchemaError(
            "field " + repr(name) + ": label must be a string of 1..120 chars")
    help_text = raw.get("description") or raw.get("help") or ""
    if not isinstance(help_text, str) or len(help_text) > 500:
        raise SettingsSchemaError(
            "field " + repr(name) + ": help must be a string of at most 500 chars")
    required = raw.get("required", False)
    if not isinstance(required, bool):
        raise SettingsSchemaError(
            "field " + repr(name) + ": required must be a boolean")
    has_default = name in defaults or "default" in raw
    default = defaults[name] if name in defaults else raw.get("default")
    spec = FieldSpec(
        name=name, type=field_type, label=label, help=help_text,
        required=required, has_default=has_default, default=default,
        minimum=minimum, maximum=maximum, min_length=min_length,
        max_length=max_length, enum=enum)
    if has_default:
        _check_default(spec)
    return spec


def _check_default(spec: FieldSpec) -> None:
    errors = _validate_field(spec, spec.default)
    if errors:
        raise SettingsSchemaError(
            "field " + repr(spec.name) + ": declared default is "
            "invalid: " + errors[0]["message"])


def _field_error(name: str, code: str, message: str) -> dict:
    return {"field": name, "code": code, "message": message}


def _validate_field(spec: FieldSpec, value) -> list[dict]:
    """Every refusal for one value, as named errors. Type
    is judged first; a wrong-typed value earns only its
    wrong_type error (range checks on it would be noise)."""
    name = spec.name
    if spec.type == "string" and not isinstance(value, str):
        return [_field_error(name, "wrong_type",
                "field " + repr(name) + " must be a string")]
    if spec.type == "integer" and not _is_int(value):
        return [_field_error(name, "wrong_type",
                "field " + repr(name) + " must be an integer")]
    if spec.type == "number" and not (
            _is_number(value) and math.isfinite(float(value))):
        return [_field_error(name, "wrong_type",
                "field " + repr(name) + " must be a finite number")]
    if spec.type == "boolean" and not isinstance(value, bool):
        return [_field_error(name, "wrong_type",
                "field " + repr(name) + " must be a boolean")]
    errors: list[dict] = []
    if spec.enum is not None and value not in spec.enum:
        errors.append(_field_error(name, "not_in_enum",
            "field " + repr(name) + " must be one of "
            + repr(list(spec.enum))))
    if spec.type in ("integer", "number"):
        if spec.minimum is not None and value < spec.minimum:
            errors.append(_field_error(name, "below_minimum",
                "field " + repr(name) + " must be at least "
                + repr(spec.minimum)))
        if spec.maximum is not None and value > spec.maximum:
            errors.append(_field_error(name, "above_maximum",
                "field " + repr(name) + " must be at most "
                + repr(spec.maximum)))
    if spec.type == "string":
        if spec.min_length is not None and len(value) < spec.min_length:
            errors.append(_field_error(name, "too_short",
                "field " + repr(name) + " must be at least "
                + str(spec.min_length) + " characters"))
        limit = spec.max_length if spec.max_length is not None else MAX_TEXT_CHARS
        if len(value) > limit:
            errors.append(_field_error(name, "too_long",
                "field " + repr(name) + " must be at most "
                + str(limit) + " characters"))
    return errors


def validate_complete(manifest, values) -> dict:
    """Validate a complete values document (design 3).
    Missing fields with defaults take the default; missing
    required fields without defaults refuse as required;
    missing optional fields without defaults stay absent.
    Returns the effective values dict."""
    specs = parse_settings_schema(manifest)
    if not isinstance(values, dict):
        raise SettingsValidationError([_field_error(
            "", "wrong_type", "settings values must be an object")])
    errors: list[dict] = []
    known = {spec.name for spec in specs}
    for key in values:
        if key not in known:
            errors.append(_field_error(str(key), "unknown_field",
                "unknown settings field: " + repr(key)))
    effective: dict = {}
    for spec in specs:
        if spec.name in values:
            value = values[spec.name]
            field_errors = _validate_field(spec, value)
            if field_errors:
                errors.extend(field_errors)
            else:
                effective[spec.name] = copy.deepcopy(value)
        elif spec.has_default:
            effective[spec.name] = copy.deepcopy(spec.default)
        elif spec.required:
            errors.append(_field_error(spec.name, "required",
                "field " + repr(spec.name) + " is required"))
    if errors:
        raise SettingsValidationError(errors)
    return effective


def apply_settings_patch(manifest, current: dict, patch) -> dict:
    """Merge a submitted patch over current effective
    values, then validate the merged document whole."""
    if not isinstance(patch, dict):
        raise SettingsValidationError([_field_error(
            "", "wrong_type", "settings patch must be an object")])
    if not isinstance(current, dict):
        raise SettingsValidationError([_field_error(
            "", "wrong_type", "current settings must be an object")])
    merged = dict(current)
    merged.update(patch)
    return validate_complete(manifest, merged)


def effective_values(manifest, stored: dict | None = None) -> dict:
    """Defaults overlaid with stored owner values, the
    merged document validated whole."""
    specs = parse_settings_schema(manifest)
    base: dict = {}
    for spec in specs:
        if spec.has_default:
            base[spec.name] = copy.deepcopy(spec.default)
    if stored:
        base.update(stored)
    return validate_complete(manifest, base)


def _manifest_meta(manifest) -> tuple[str, str]:
    if isinstance(manifest, dict):
        return str(manifest.get("id", "")), str(manifest.get("name", ""))
    return str(getattr(manifest, "id", "")), str(getattr(manifest, "name", ""))


def build_settings_form(manifest, values: dict | None = None) -> dict:
    """The generated form document (design section 2).
    values are STORED owner values (or None); the form
    carries effective values (defaults overlaid)."""
    specs = parse_settings_schema(manifest)
    plugin_id, plugin_name = _manifest_meta(manifest)
    effective = effective_values(manifest, values)
    fields = [spec.to_dict(effective.get(spec.name)) for spec in specs]
    has = len(specs) > 0
    return {
        "format": FORM_FORMAT, "form_version": FORM_VERSION,
        "plugin_id": plugin_id, "plugin_name": plugin_name,
        "has_settings": has,
        "status": "ok" if has else "no_settings",
        "message": ("" if has else
            "This plugin declares no settings."),
        "fields": fields,
        "values": effective,
        "schema": copy.deepcopy(declared_schema(manifest)),
        "defaults": declared_defaults(manifest),
    }


def render_settings_form_html(form: dict) -> str:
    """Deterministic HTML for a form document: one control
    per field, every attribute from the form data, every
    text value escaped. The no-settings form renders one
    honest paragraph and no controls."""
    plugin_id = html.escape(str(form.get("plugin_id", "")), quote=True)
    out: list[str] = []
    out.append('<form class="plugin-settings" data-plugin-id="'
               + plugin_id + '" method="post">')
    if not form.get("has_settings"):
        out.append('<p class="no-settings">'
                   + html.escape(str(form.get("message", ""))) + "</p>")
        out.append("</form>")
        return "\n".join(out)
    for field in form.get("fields", []):
        out.append(_render_field_html(field))
    out.append("</form>")
    return "\n".join(out)


def _render_field_html(field: dict) -> str:
    name = html.escape(str(field["name"]), quote=True)
    label = html.escape(str(field["label"]))
    widget = field["widget"]
    value = field.get("value")
    constraints = field.get("constraints") or {}
    parts: list[str] = ['<div class="settings-field" data-field="'
                        + name + '">']
    parts.append('<label for="ps-' + name + '">' + label + "</label>")
    if widget == "select":
        parts.append('<select id="ps-' + name + '" name="' + name + '">')
        for option in constraints.get("enum") or []:
            opt = html.escape(str(option), quote=True)
            text = html.escape(str(option))
            selected = " selected" if option == value else ""
            parts.append('<option value="' + opt + '"' + selected
                         + ">" + text + "</option>")
        parts.append("</select>")
    elif widget == "checkbox":
        checked = " checked" if value is True else ""
        parts.append('<input type="checkbox" id="ps-' + name
                     + '" name="' + name + '"' + checked + ">")
    elif widget == "number":
        attrs = ""
        if constraints.get("minimum") is not None:
            attrs += ' min="' + html.escape(str(constraints["minimum"]), quote=True) + '"'
        if constraints.get("maximum") is not None:
            attrs += ' max="' + html.escape(str(constraints["maximum"]), quote=True) + '"'
        step = "1" if field["type"] == "integer" else "any"
        shown = "" if value is None else html.escape(str(value), quote=True)
        parts.append('<input type="number" id="ps-' + name + '" name="'
                     + name + '" value="' + shown + '" step="' + step
                     + '"' + attrs + ">")
    else:
        shown = "" if value is None else html.escape(str(value), quote=True)
        parts.append('<input type="text" id="ps-' + name + '" name="'
                     + name + '" value="' + shown + '">')
    if field.get("help"):
        parts.append('<small class="settings-help">'
                     + html.escape(str(field["help"])) + "</small>")
    parts.append("</div>")
    return "".join(parts)


# -- The declared storage road (P-089 idiom, design 4) ---------------------


def _check_user_id(user_id) -> str:
    if not isinstance(user_id, str) or not user_id:
        raise SettingsError("invalid user_id: " + repr(user_id))
    try:
        uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        raise SettingsError("invalid user_id: " + repr(user_id)) from None
    return user_id


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    _check_user_id(user_id)
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / (user_id + ".json")


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "plugins": {}}


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsStoreError(
            "plugin settings store is unreadable: " + str(exc)) from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("plugins"), dict):
        raise SettingsStoreError("plugin settings store has an unknown shape")
    return doc


def _save_doc(user_id: str, doc: dict, base_dir: Path | None = None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _stored_section(doc: dict, plugin_id: str) -> dict | None:
    section = doc["plugins"].get(plugin_id)
    if section is None:
        return None
    if not isinstance(section, dict) or not isinstance(section.get("values"), dict):
        raise SettingsStoreError(
            "stored settings for plugin " + repr(plugin_id)
            + " have an unknown shape")
    return section


def load_stored_values(user_id: str, plugin_id: str,
                       base_dir: Path | None = None) -> dict | None:
    """Stored owner values for one plugin, or None. The
    raw stored document; schema validation happens in
    get_plugin_settings against the current declaration."""
    doc = _load_doc(user_id, base_dir)
    section = _stored_section(doc, plugin_id)
    if section is None:
        return None
    return copy.deepcopy(section["values"])


def get_plugin_settings(user_id: str, manifest,
                        base_dir: Path | None = None) -> dict:
    """Effective values for one owner + plugin: declared
    defaults overlaid with stored values, validated whole
    against the CURRENT schema. Stored values the schema
    no longer accepts raise SettingsStoreError naming the
    refusal - never silently dropped."""
    plugin_id, _name = _manifest_meta(manifest)
    stored = load_stored_values(user_id, plugin_id, base_dir)
    try:
        return effective_values(manifest, stored)
    except SettingsValidationError as exc:
        raise SettingsStoreError(
            "stored settings for plugin " + repr(plugin_id)
            + " no longer validate: " + str(exc)) from exc


def save_plugin_settings(user_id: str, manifest, patch,
                         base_dir: Path | None = None) -> dict:
    """The generated UI's write road: validate the patch
    against the declared schema (merged over the current
    effective values, validated whole), persist the
    complete effective values, and return them with the
    regenerated form. A refused patch writes NOTHING."""
    plugin_id, _name = _manifest_meta(manifest)
    if not parse_settings_schema(manifest):
        raise SettingsValidationError([_field_error(
            "", "no_settings",
            "plugin " + repr(plugin_id) + " declares no settings")])
    current = get_plugin_settings(user_id, manifest, base_dir)
    effective = apply_settings_patch(manifest, current, patch)
    doc = _load_doc(user_id, base_dir)
    doc["plugins"][plugin_id] = {
        "values": copy.deepcopy(effective), "updated_at": _now_iso()}
    _save_doc(user_id, doc, base_dir)
    return {"plugin_id": plugin_id, "values": copy.deepcopy(effective),
            "form": build_settings_form(manifest, effective)}


def form_for_owner(user_id: str, manifest,
                   base_dir: Path | None = None) -> dict:
    stored = load_stored_values(user_id, _manifest_meta(manifest)[0], base_dir)
    return build_settings_form(manifest, stored)


def export_plugin_settings(user_id: str, manifest,
                           base_dir: Path | None = None) -> dict:
    """Custody export (P-094 rules): one checksummed
    document carrying the plugin's effective + stored
    settings and its declaration, or an honest empty."""
    plugin_id, _name = _manifest_meta(manifest)
    stored = load_stored_values(user_id, plugin_id, base_dir)
    effective = get_plugin_settings(user_id, manifest, base_dir)
    sections = [{
        "name": "settings", "kind": "plugin_settings",
        "status": "exported" if stored is not None else "empty",
        "values": effective, "stored": stored}]
    core = {"plugin_id": plugin_id, "owner_id": user_id,
            "sections": sections}
    return {
        "format": EXPORT_FORMAT, "export_version": EXPORT_VERSION,
        "kind": "plugin_settings_export", "plugin_id": plugin_id,
        "owner_id": user_id, "exported_at": _now_iso(),
        "schema": copy.deepcopy(declared_schema(manifest)),
        "defaults": declared_defaults(manifest),
        "sections": sections, "content_sha256": _checksum(core)}


def verify_export_checksum(document: dict) -> bool:
    if not isinstance(document, dict):
        return False
    core = {"plugin_id": document.get("plugin_id"),
            "owner_id": document.get("owner_id"),
            "sections": document.get("sections")}
    return document.get("content_sha256") == _checksum(core)


def delete_plugin_settings(user_id: str, plugin_id: str,
                           base_dir: Path | None = None) -> dict:
    """Custody delete: exactly this plugin's section goes;
    every other plugin and owner is untouched."""
    _check_user_id(user_id)
    doc = _load_doc(user_id, base_dir)
    section = doc["plugins"].pop(plugin_id, None)
    if section is not None:
        _save_doc(user_id, doc, base_dir)
    return {"plugin_id": plugin_id, "owner_id": user_id,
            "deleted": section is not None,
            "removed": {"settings_sections": 1 if section is not None else 0}}


#: Shipped citizens whose manifests the HTTP road can
#: resolve without a registration (the P-094 pattern).
CITIZEN_MANIFEST_MODULES = {
    "runmal.summarise": "runmal.plugins.summarise",
    "runmal.vector-storage": "runmal.plugins.vector_storage",
    "runmal.translate": "runmal.plugins.translate",
    "runmal.image-generation": "runmal.plugins.image_generation",
    "runmal.web-search": "runmal.plugins.web_search",
    "runmal.quick-replies": "runmal.plugins.quick_replies",
    "runmal.regex-scripts": "runmal.plugins.regex_scripts",
    "runmal.tts": "runmal.plugins.tts",
    "runmal.stt": "runmal.plugins.stt",
    "runmal.expressions": "runmal.plugins.expressions",
    "runmal.variables": "runmal.plugins.variables",
    "runmal.plugin-custody": "runmal.plugins.custody",
    "runmal.gallery": "runmal.plugins.gallery",
    "runmal.game-bridge": "runmal.plugins.game_bridge",
    PLUGIN_ID: "runmal.plugins.settings_ui",
}


def resolve_manifest(registry, plugin_id: str):
    """Registry record first, else a shipped citizen's
    manifest, else None (the caller answers 404)."""
    if registry is not None:
        record = registry.find(plugin_id) if hasattr(registry, "find") else None
        if record is not None:
            return record.manifest
    module_path = CITIZEN_MANIFEST_MODULES.get(plugin_id)
    if module_path is None:
        return None
    import importlib
    try:
        module = importlib.import_module(module_path)
        return module.build_manifest()
    except Exception:
        return None


def settings_ui_coverage() -> dict:
    return {"format": FORM_FORMAT, "form_version": FORM_VERSION,
            "plugin_id": PLUGIN_ID, "store_schema": STORE_SCHEMA,
            "field_types": sorted(FIELD_TYPES),
            "citizens": sorted(CITIZEN_MANIFEST_MODULES)}


# -- The P-081 citizen -------------------------------------------------------


def manifest_data() -> dict:
    return {
        "id": PLUGIN_ID, "name": "Plugin Settings",
        "version": PLUGIN_VERSION, "api_version": 1,
        "description": "Plugin settings UI generated from "
                       "declared schemas: one renderer for "
                       "every plugin's settings.",
        "author": "Runmal",
        "capabilities": ["ui.slots"],
        "permissions": ["ui.contribute"],
        "events": [], "prompt_hooks": [],
        "ui_slots": [{
            "id": UI_LOCAL_ID, "slot": "settings.panel",
            "label": "Plugin Settings", "order": 121,
            "payload": {"kind": "panel", "route": "plugin-settings"}}],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest():
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    return grants_from_manifest(manifest_to_data(build_manifest()))


class SettingsUiPlugin:
    """The citizen: a settings-panel contribution only.
    The renderer, validation and store are module
    functions (trusted host wiring); the citizen itself
    declares no settings and holds no data."""

    @property
    def manifest(self):
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    async def on_event(self, event) -> None:
        return None


def register_plugin(registry: PluginRegistry, *,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, SettingsUiPlugin]:
    plugin = SettingsUiPlugin()
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "CITIZEN_MANIFEST_MODULES", "EXPORT_FORMAT", "EXPORT_VERSION",
    "FIELD_TYPES", "FORM_FORMAT", "FORM_VERSION", "PLUGIN_ID",
    "PLUGIN_VERSION", "STORE_DIR_NAME", "STORE_SCHEMA",
    "UI_LOCAL_ID", "VERSION", "FieldSpec", "SettingsError",
    "SettingsSchemaError", "SettingsStoreError",
    "SettingsUiPlugin", "SettingsValidationError",
    "apply_settings_patch", "build_manifest",
    "build_settings_form", "declared_defaults",
    "declared_schema", "delete_plugin_settings",
    "effective_values", "export_plugin_settings",
    "form_for_owner", "get_plugin_settings", "load_stored_values",
    "manifest_data", "parse_settings_schema", "register_plugin",
    "render_settings_form_html", "resolve_manifest",
    "sandbox_grants", "save_plugin_settings", "settings_block",
    "settings_ui_coverage", "store_path", "validate_complete",
    "verify_export_checksum",
]
