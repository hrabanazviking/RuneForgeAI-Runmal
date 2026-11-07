"""Per-backend parameter compatibility filtering (S208).

Translates the canonical sampling bag (S207) into a backend's wire shape,
deterministically. Nothing is silently lost: every input parameter ends up
either in the output ``params``, in ``mapped`` (renamed, same value), or in
``dropped`` (with an explicit reason). Provider quirks live here and only
here, behind the backend seam.

P-053 alignment: the profiles below are kept in exact agreement with
the adapters' own declared sampler sets (Ollama serves ``min_p`` and
``context_length`` — mapped to ``min_p`` / ``num_ctx`` here exactly as
the adapter's own options mapping does; OpenAI's unserved canonical
controls carry named reasons instead of the generic unknown-parameter
drop). ``runmal.backends.capabilities.audit_truth`` pins the agreement
so the two truth sources cannot drift apart again silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParamMapping:
    source: str
    dest: str
    value: object


@dataclass(frozen=True)
class ParamDrop:
    param: str
    value: object
    reason: str


@dataclass(frozen=True)
class CompatibilityResult:
    backend: str
    params: dict = field(default_factory=dict)
    kept: tuple[str, ...] = ()
    mapped: tuple[ParamMapping, ...] = ()
    dropped: tuple[ParamDrop, ...] = ()


@dataclass(frozen=True)
class BackendProfile:
    name: str
    # canonical name -> wire name (identity = pass-through)
    wire_names: dict[str, str]
    # canonical name -> explicit drop reason
    unsupported: dict[str, str]


OPENAI_PROFILE = BackendProfile(
    name="openai",
    wire_names={
        "temperature": "temperature",
        "top_p": "top_p",
        "max_tokens": "max_tokens",
        "frequency_penalty": "frequency_penalty",
        "presence_penalty": "presence_penalty",
        "stop": "stop",
        "seed": "seed",
    },
    unsupported={
        "top_k": "OpenAI chat completions has no top_k parameter",
        "min_p": "OpenAI chat completions has no min_p parameter",
        "repetition_penalty": (
            "OpenAI uses frequency_penalty/presence_penalty instead"
        ),
        "context_length": (
            "context length is a model property on OpenAI chat "
            "completions, not a per-request parameter"
        ),
    },
)

OLLAMA_PROFILE = BackendProfile(
    name="ollama",
    wire_names={
        "temperature": "temperature",
        "top_p": "top_p",
        "top_k": "top_k",
        "min_p": "min_p",
        "seed": "seed",
        "stop": "stop",
        "max_tokens": "num_predict",
        "repetition_penalty": "repeat_penalty",
        "context_length": "num_ctx",
    },
    unsupported={
        "frequency_penalty": "Ollama options have no frequency_penalty",
        "presence_penalty": "Ollama options have no presence_penalty",
    },
)

PROFILES: dict[str, BackendProfile] = {
    OPENAI_PROFILE.name: OPENAI_PROFILE,
    OLLAMA_PROFILE.name: OLLAMA_PROFILE,
}


def filter_params(params: dict, profile: BackendProfile) -> CompatibilityResult:
    """Translate ``params`` for ``profile``; pure and deterministic."""
    out: dict = {}
    kept: list[str] = []
    mapped: list[ParamMapping] = []
    dropped: list[ParamDrop] = []
    for key in sorted(params):
        value = params[key]
        if key in profile.wire_names:
            dest = profile.wire_names[key]
            out[dest] = value
            if dest != key:
                mapped.append(ParamMapping(key, dest, value))
            else:
                kept.append(key)
        elif key in profile.unsupported:
            dropped.append(ParamDrop(key, value, profile.unsupported[key]))
        else:
            dropped.append(
                ParamDrop(key, value, "unknown parameter is not forwarded")
            )
    return CompatibilityResult(
        backend=profile.name,
        params=out,
        kept=tuple(kept),
        mapped=tuple(mapped),
        dropped=tuple(dropped),
    )


def filter_for_backend(params: dict, backend: str) -> CompatibilityResult:
    """Filter by backend name; unknown backend names are an error."""
    try:
        profile = PROFILES[backend]
    except KeyError as exc:
        raise ValueError(f"unknown backend: {backend!r}") from exc
    return filter_params(params, profile)
