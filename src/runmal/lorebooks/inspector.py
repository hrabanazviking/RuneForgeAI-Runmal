"""Activation inspector (P-043): "why did this entry fire".

Roadmap line: *Activation inspector: "why did this entry fire" --
the matched keys and roll shown per message (Part XIII's
Inspector consumes this).*

This module is the explanation layer over the existing engine.
It invents no activation behaviour of its own: the canonical
outcome of a tick comes from :func:`preview_activation` (the
same pipeline the editor preview and the prompt inspector run),
and every other fact is recomputed with the engine's own public
cores -- the P-037 windowed scan (matched keys, message and
external indices, selective logic, recursion depth and
``triggered_by``), the P-043 near-miss scan (primary matched,
secondary gate refused), and the matcher's recorded scores.
The output is DATA -- one explanation dict per entry, a
per-message breakdown, and tick totals -- so Part XIII's
Inspector (and any other consumer) renders it without
re-deriving anything.

Per entry the explanation carries, to the extent the engine's
records carry each fact:

- the outcome (``status`` -- the preview vocabulary: included /
  discarded / not_triggered / group_excluded / disabled) plus a
  single deterministic ``reason`` code and a one-sentence
  ``summary`` built only from recorded facts;
- keys: every declared primary/secondary key, which matched and
  which did not, the P-032 selective logic, the secondary counts
  and the gate verdict, and WHERE the matches landed
  (``message_indices`` into the full message list,
  ``external_indices`` into the external segment);
- probability (P-036): the stored percent and the recorded roll
  (seed, context, value, passed, seeded) -- or None for ungated
  entries, which make no roll by design;
- inclusion groups (P-034): the group, the entry's weight, the
  winner's id and the winner's weight/priority when excluded;
- timed effects (P-033): the config always; the live counters
  and the derived effect ONLY when the caller supplied
  ``entry_states`` (see preview.py's P-043 note -- a clean-state
  inspection records no counters and says so);
- recursion (P-031): the activation ``via``, the scan depth and
  the ``triggered_by`` parent for recursive hits, the reference
  depth for ``{{lore:...}}`` expansions;
- vector matching (P-041): the recorded cosine ``vector_score``,
  the threshold the inspector itself applied (when it ran the
  matcher), the matcher mode/degradation, and whether the firing
  was a true vector hit or the honestly-labelled keyword
  fallback;
- scope (P-040): the layer stamped from the caller's ``scope``
  argument (a single-book inspection knows no layer of its own);
- budget & placement (P-037/P-038, S204): tokens, the budget
  verdict (``discard_reason``: over_budget / probability_skip /
  scope_over_budget when a layered preview is explained), the
  declared position and the effective role / injection depth.

Near misses are first-class: an entry that almost fired carries
``near_miss: True``, a ``near_miss_kind`` and the stage it
reached (``stage_reached``). The near-miss kinds are
``secondary_gate_failed``, ``cooldown_suppressed``,
``delay_armed``, ``delay_pending``, ``vector_below_threshold``,
``probability_skip``, ``over_budget``, ``scope_over_budget``
and ``inclusion_group_excluded``.

Honesty (what the engine does NOT record -- also returned in
the payload's ``facts_not_recorded``): probability rolls exist
only for gated entries; vector scores exist only when the
matcher ran (caller-supplied ``vector_hit_ids`` carry no
scores, and a precomputed matcher outcome does not record the
threshold it used); recursive-round (depth > 0) secondary-gate
near misses are not recorded -- the near-miss scan covers the
round-0 window only; ``{{lore:...}}`` reference provenance
records via/depth, not the referring entry's name; timed
counters exist only when ``entry_states`` are supplied; scope
over-budget outcomes are produced by the P-040 layered pass,
so they appear when a layered preview dict is explained via
:func:`explain_preview`, not from a single-book tick.
"""

from __future__ import annotations

from runmal.lorebooks.groups import (
    normalise_group_weight,
    normalise_inclusion_group,
)
from runmal.lorebooks.logic import secondary_gate
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    ScanEntry,
    scan_entries_recursive,
    scan_entries_windowed,
    scan_near_misses,
)
from runmal.lorebooks.vector_match import (
    DEFAULT_VECTOR_THRESHOLD,
    match_vectorised_sync,
)
from runmal.lorebooks.windows import ScanSettings, build_scan_window

#: Payload schema tag; Part XIII's Inspector keys on this.
INSPECT_SCHEMA = "runmal-p043-activation-inspection-v1"

FACTS_NOT_RECORDED = (
    "probability rolls exist only for gated entries (probability < 100); ungated entries make no roll by design (P-036)",
    "vector scores exist only when the vector matcher ran; caller-supplied vector_hit_ids carry no scores, and a precomputed matcher outcome does not record the threshold it used",
    "recursive-round (depth > 0) secondary-gate near misses are not recorded; the near-miss scan covers the round-0 scan window only",
    "reference-expansion ({{lore:...}}) provenance records via and depth only; the referring entry is not recorded by the activation engine",
    "timed-effect counters are reported only when entry_states are supplied; a clean-state inspection records the config and no live counters",
    "scope_over_budget outcomes are produced by the P-040 layered pass and appear when a layered preview dict is explained, not from a single-book inspection",
)

_INCLUDED_REASONS = {
    "constant": "constant_active",
    "key": "keyword_match",
    "sticky": "sticky_carryover",
    "delay": "delay_fired",
    "reference": "reference_expansion",
    "recursive": "recursive_trigger",
    "vector": "vector_match",
    "vector_fallback": "keyword_fallback",
}

_NEAR_MISS_KINDS = frozenset(
    {
        "secondary_gate_failed",
        "cooldown_suppressed",
        "delay_armed",
        "delay_pending",
        "vector_below_threshold",
        "probability_skip",
        "over_budget",
        "scope_over_budget",
        "inclusion_group_excluded",
    }
)

__all__ = [
    "INSPECT_SCHEMA",
    "FACTS_NOT_RECORDED",
    "explain_preview",
    "inspect_activation",
]


def _unmatched(declared, matched) -> list:
    matched_set = set(matched)
    return [k for k in declared if k not in matched_set]


def _summary(entry_name: str, reason: str, facts: dict) -> str:
    """One deterministic sentence built only from recorded facts."""
    name = entry_name or "(unnamed)"
    if reason == "keyword_match":
        keys = ", ".join(facts["matched_primary"]) or "?"
        return f"{name} fired: primary key(s) [{keys}] matched."
    if reason == "constant_active":
        return f"{name} fired: it is a constant entry (no key needed)."
    if reason == "sticky_carryover":
        return f"{name} fired: sticky carryover from an earlier trigger."
    if reason == "delay_fired":
        return f"{name} fired: its armed delay reached zero this tick."
    if reason == "reference_expansion":
        return f"{name} fired: pulled in by a {{{{lore:...}}}} reference."
    if reason == "recursive_trigger":
        return f"{name} fired: a fired entry's content matched its key(s) (recursive scan)."
    if reason == "vector_match":
        return f"{name} fired: vector similarity {facts.get('vector_score')} reached the threshold."
    if reason == "keyword_fallback":
        keys = ", ".join(facts["matched_primary"]) or "?"
        return f"{name} fired by keyword fallback (embeddings degraded): key(s) [{keys}] matched."
    if reason == "probability_skip":
        roll = facts.get("roll") or {}
        return (
            f"{name} matched but its probability roll {roll.get('roll')} "
            f"did not pass the {roll.get('probability')} gate."
        )
    if reason == "over_budget":
        return f"{name} matched but its {facts.get('tokens')} tokens did not fit the remaining budget."
    if reason == "scope_over_budget":
        return f"{name} matched but its scope layer's budget was already spent."
    if reason == "inclusion_group_excluded":
        return (
            f"{name} fired but lost inclusion group "
            f"'{facts.get('inclusion_group')}' to entry {facts.get('group_winner_id')}."
        )
    if reason == "secondary_gate_failed":
        return (
            f"{name} almost fired: primary key(s) "
            f"[{', '.join(facts['matched_primary'])}] matched but selective "
            f"logic '{facts.get('selective_logic')}' refused "
            f"({facts.get('matched_secondary_count')} of "
            f"{facts.get('secondary_count')} secondary keys matched)."
        )
    if reason == "cooldown_suppressed":
        return f"{name} matched but a running cooldown suppressed it this tick."
    if reason == "delay_armed":
        return f"{name} matched; its delay is now armed and it will fire when the countdown ends."
    if reason == "delay_pending":
        return f"{name} is waiting out an armed delay from an earlier match."
    if reason == "vector_below_threshold":
        return f"{name} did not fire: vector similarity {facts.get('vector_score')} stayed below the threshold and no fallback hit replaced it."
    if reason == "vector_no_match":
        return f"{name} did not fire: it is vectorised and no vector hit (and no keyword fallback hit) landed."
    if reason == "disabled":
        return f"{name} is disabled and never fires."
    if reason == "no_key_match":
        return f"{name} did not fire: no primary key matched in the scan window."
    return f"{name}: {reason}."


def explain_preview(
    preview: dict,
    entries: list,
    *,
    hits=(),
    near_misses=(),
    scope: str | None = None,
    lorebook_id: str | None = None,
    vector_threshold=None,
) -> dict:
    """Explain one preview-shaped tick as inspector data. PURE.

    ``preview`` is a :func:`preview_activation` result (a P-040
    layered preview layer dict works too -- its rows carry the
    same fields plus scope data, and its ``scope_over_budget``
    discards explain themselves). ``hits`` are the tick's
    ScanHits (windowed or recursive) and ``near_misses`` its
    NearMiss rows; both are recomputed by
    :func:`inspect_activation` with the engine's own cores --
    callers explaining a stored preview may omit them, and the
    key/where facts they alone carry are then reported as
    unrecorded for that call rather than invented.
    """
    scan_by_id = {}
    for entry in entries:
        try:
            view = ScanEntry.from_orm(entry)
        except Exception:
            continue
        scan_by_id[view.id] = view
    entry_by_id = {str(e.id): e for e in entries}
    hit_by_id = {h.entry_id: h for h in hits}
    near_by_id = {m.entry_id: m for m in near_misses}
    vector_summary = preview.get("vector_match") or {}

    explanations: list[dict] = []
    for row in preview.get("entries", []):
        entry_id = row["entry_id"]
        entry = entry_by_id.get(entry_id)
        view = scan_by_id.get(entry_id)
        hit = hit_by_id.get(entry_id)
        near = near_by_id.get(entry_id)
        status = row["status"]
        via = row.get("via")

        declared_primary = list(view.keys) if view is not None else []
        declared_secondary = list(view.secondary_keys) if view is not None else []
        matched_primary = list(row.get("matched_primary") or [])
        matched_secondary = list(row.get("matched_secondary") or [])
        if hit is not None:
            matched_primary = list(hit.matched_primary) or matched_primary
            matched_secondary = list(hit.matched_secondary) or matched_secondary
        if near is not None:
            # A gate refusal is a near miss, not a hit: the preview
            # row carries no matched keys for it, so the near-miss
            # record is the only honest source of what matched.
            matched_primary = matched_primary or list(near.matched_primary)
            matched_secondary = matched_secondary or list(near.matched_secondary)
        selective_logic = (
            hit.selective_logic
            if hit is not None
            else (near.selective_logic if near is not None else (view.selective_logic if view is not None else "and_any"))
        )
        secondary_count = len([k for k in declared_secondary if isinstance(k, str) and k.strip()])
        if near is not None:
            gate = "failed"
        elif secondary_count == 0:
            gate = "no_secondary_keys"
        elif hit is not None:
            gate = "passed"
        elif matched_primary:
            gate = "failed"
        else:
            gate = "not_evaluated"

        timed = row.get("timed")
        timed_block = {
            "config": {
                "sticky_prompts": int(getattr(entry, "sticky_prompts", 0) or 0) if entry is not None else 0,
                "cooldown_prompts": int(getattr(entry, "cooldown_prompts", 0) or 0) if entry is not None else 0,
                "delay_prompts": int(getattr(entry, "delay_prompts", 0) or 0) if entry is not None else 0,
            },
            "recorded": timed is not None,
            "state_before": timed["state_before"] if timed else None,
            "state_after": timed["state_after"] if timed else None,
            "effect": timed["effect"] if timed else None,
        }

        winner_id = row.get("group_winner_id")
        winner = entry_by_id.get(winner_id) if winner_id else None
        group_block = {
            "inclusion_group": row.get("inclusion_group") or normalise_inclusion_group(getattr(entry, "inclusion_group", None)) if entry is not None else row.get("inclusion_group"),
            "group_weight": row.get("group_weight"),
            "winner_id": winner_id,
            "winner_group_weight": (normalise_group_weight(getattr(winner, "group_weight", None)) if winner is not None else None),
            "winner_priority": (int(getattr(winner, "priority", 0) or 0) if winner is not None else None),
        }

        # Reason + near-miss classification (deterministic order).
        timed_effect = timed_block["effect"]
        if status == "disabled":
            reason, stage = "disabled", "none"
        elif status == "included":
            reason = _INCLUDED_REASONS.get(via or "", "included")
            stage = "included"
        elif status == "discarded":
            reason = row.get("discard_reason") or "discarded"
            stage = "budget"
        elif status == "group_excluded":
            reason, stage = "inclusion_group_excluded", "group"
        elif near is not None:
            reason, stage = "secondary_gate_failed", "gate"
        elif timed_effect in ("cooldown_suppressed", "delay_armed", "delay_pending"):
            reason, stage = timed_effect, "activation"
        elif row.get("vectorised") and row.get("vector_score") is not None:
            reason, stage = "vector_below_threshold", "vector"
        elif row.get("vectorised"):
            reason, stage = "vector_no_match", "vector"
        else:
            reason, stage = "no_key_match", "none"
        near_miss_kind = reason if reason in _NEAR_MISS_KINDS else None

        facts = {
            "matched_primary": matched_primary,
            "matched_secondary_count": len(matched_secondary),
            "secondary_count": secondary_count,
            "selective_logic": selective_logic,
            "roll": row.get("probability_roll"),
            "tokens": row.get("tokens"),
            "vector_score": row.get("vector_score"),
            "inclusion_group": group_block["inclusion_group"],
            "group_winner_id": winner_id,
        }
        explanations.append(
            {
                "entry_id": entry_id,
                "name": row.get("name", ""),
                "lorebook_id": lorebook_id if lorebook_id is not None else row.get("lorebook_id"),
                "scope": scope if scope is not None else row.get("scope"),
                "status": status,
                "fired": status == "included",
                "reason": reason,
                "summary": _summary(row.get("name", ""), reason, facts),
                "near_miss": near_miss_kind is not None,
                "near_miss_kind": near_miss_kind,
                "stage_reached": stage,
                "via": via,
                "activation_kind": row.get("activation_kind"),
                "enabled": row.get("enabled"),
                "constant": row.get("constant"),
                "keys": {
                    "primary": declared_primary,
                    "secondary": declared_secondary,
                    "matched_primary": matched_primary,
                    "matched_secondary": matched_secondary,
                    "unmatched_primary": _unmatched(declared_primary, matched_primary),
                    "unmatched_secondary": _unmatched(declared_secondary, matched_secondary),
                    "selective_logic": selective_logic,
                    "secondary_count": secondary_count,
                    "matched_secondary_count": len(matched_secondary),
                    "gate": gate,
                    "message_indices": list(hit.message_indices) if hit is not None else (list(near.message_indices) if near is not None else []),
                    "external_indices": list(row.get("external_indices") or []) or (list(near.external_indices) if near is not None else []),
                },
                "probability": {
                    "percent": row.get("probability"),
                    "roll": row.get("probability_roll"),
                },
                "group": group_block,
                "timed": timed_block,
                "recursion": {
                    "depth": row.get("depth"),
                    "triggered_by": hit.triggered_by if hit is not None else None,
                    "recursive": bool(hit is not None and hit.depth > 0) or via == "recursive",
                },
                "vector": {
                    "vectorised": row.get("vectorised"),
                    "score": row.get("vector_score"),
                    "threshold": vector_threshold,
                    "mode": vector_summary.get("mode"),
                    "degraded": vector_summary.get("degraded"),
                    "fallback_reason": vector_summary.get("fallback_reason"),
                    "fallback": via == "vector_fallback",
                },
                "placement": {
                    "position": row.get("position"),
                    "role": row.get("role"),
                    "injection_depth": row.get("injection_depth"),
                },
                "budget": {
                    "tokens": row.get("tokens"),
                    "discard_reason": row.get("discard_reason"),
                    "priority": (int(getattr(entry, "priority", 0) or 0) if entry is not None else None),
                },
                "content": row.get("content"),
            }
        )

    per_message: dict[int, dict] = {}
    for hit in hits:
        for idx in hit.message_indices:
            slot = per_message.setdefault(idx, {"index": idx, "entries": []})
            slot["entries"].append(
                {
                    "entry_id": hit.entry_id,
                    "matched_primary": list(hit.matched_primary),
                    "matched_secondary": list(hit.matched_secondary),
                }
            )
    for miss in near_misses:
        for idx in miss.message_indices:
            slot = per_message.setdefault(idx, {"index": idx, "entries": []})
            slot["entries"].append(
                {
                    "entry_id": miss.entry_id,
                    "matched_primary": list(miss.matched_primary),
                    "matched_secondary": list(miss.matched_secondary),
                    "near_miss": "secondary_gate_failed",
                }
            )

    totals = {
        "entries": len(explanations),
        "included": sum(1 for e in explanations if e["status"] == "included"),
        "discarded": sum(1 for e in explanations if e["status"] == "discarded"),
        "not_triggered": sum(1 for e in explanations if e["status"] == "not_triggered"),
        "group_excluded": sum(1 for e in explanations if e["status"] == "group_excluded"),
        "disabled": sum(1 for e in explanations if e["status"] == "disabled"),
        "near_misses": sum(1 for e in explanations if e["near_miss"]),
    }
    result: dict = {
        "schema": INSPECT_SCHEMA,
        "lorebook_id": lorebook_id,
        "scope": scope,
        "scan_depth": preview.get("scan_depth"),
        "scan_mode": preview.get("scan_mode"),
        "scan_external_context": preview.get("scan_external_context"),
        "scan_window": preview.get("scan_window"),
        "token_budget": preview.get("token_budget"),
        "tokens_used": preview.get("tokens_used"),
        "seed": preview.get("seed"),
        "roll_context": preview.get("roll_context"),
        "timed_states_supplied": bool(preview.get("timed_states_supplied", False)),
        "totals": totals,
        "entries": explanations,
        "messages": [per_message[idx] for idx in sorted(per_message)],
        "facts_not_recorded": list(FACTS_NOT_RECORDED),
    }
    if "probability_rolls" in preview:
        result["probability_rolls"] = preview["probability_rolls"]
    if "inclusion_group_winners" in preview:
        result["inclusion_group_winners"] = preview["inclusion_group_winners"]
    if "vector_match" in preview:
        result["vector_match"] = preview["vector_match"]
    if preview.get("recursive_scan"):
        result["recursive_scan"] = True
        result["max_recursion_depth"] = preview.get("max_recursion_depth")
        result["recursion_depth_reached"] = preview.get("recursion_depth_reached")
        result["recursion_budget_exhausted"] = preview.get("recursion_budget_exhausted")
    return result


def inspect_activation(
    entries: list,
    messages: list[str],
    scan_depth: int,
    token_budget: int | None,
    seed: int | None = None,
    *,
    roll_context: str = "",
    recursive_scan: bool = False,
    max_recursion_depth: int = MAX_RECURSIVE_SCAN_DEPTH,
    vector_hit_ids: set[str] | None = None,
    vector_match=None,
    vector_embedder=None,
    vector_threshold=None,
    vector_max_entries=None,
    scan_mode: str | None = None,
    scan_external_context: bool | None = None,
    external_context: list[str] | None = None,
    entry_states: dict | None = None,
    scope: str | None = None,
    lorebook_id: str | None = None,
) -> dict:
    """Inspect one activation tick: preview outcome + explanation.

    Mirrors :func:`preview_activation`'s signature and semantics
    (plus ``entry_states`` / ``scope`` / ``lorebook_id``) and
    returns the :func:`explain_preview` payload for the tick.
    The vector matcher is resolved exactly as the preview
    resolves it, so the explanation and the outcome can never
    drift: a caller-supplied ``vector_match`` wins, then an
    explicit ``vector_hit_ids`` set, then the sync embedder.
    """
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")

    settings = ScanSettings.normalised(
        scan_depth=scan_depth,
        scan_mode=scan_mode,
        scan_external_context=scan_external_context,
    )
    external_texts = list(external_context or ())

    effective_threshold = vector_threshold
    if vector_match is not None:
        if vector_hit_ids is None:
            vector_hit_ids = set(vector_match.hit_ids)
    elif vector_hit_ids is None and vector_embedder is not None:
        vector_match = match_vectorised_sync(
            entries,
            list(messages),
            vector_embedder,
            threshold=vector_threshold,
            max_entries=vector_max_entries,
            settings=settings,
            external_context=external_texts,
        )
        vector_hit_ids = set(vector_match.hit_ids)
        if effective_threshold is None:
            effective_threshold = DEFAULT_VECTOR_THRESHOLD
    if vector_match is not None and not vector_match.candidates:
        vector_match = None

    scan_view = [ScanEntry.from_orm(e) for e in entries]
    if recursive_scan:
        recursive_result = scan_entries_recursive(
            scan_view,
            list(messages),
            scan_depth,
            max_recursion_depth=max_recursion_depth,
            token_budget=token_budget,
            settings=settings,
            external_context=external_texts,
        )
        hits = list(recursive_result.hits)
    else:
        hits = scan_entries_windowed(
            scan_view, list(messages), settings, external_texts
        )
    hit_by_id = {h.entry_id: h for h in hits}
    if vector_match is not None:
        for fb_hit in vector_match.keyword_hits:
            hit_by_id.setdefault(fb_hit.entry_id, fb_hit)
    near_misses = scan_near_misses(
        scan_view, list(messages), settings, external_texts
    )

    preview = preview_activation(
        entries,
        messages,
        scan_depth,
        token_budget,
        seed=seed,
        roll_context=roll_context,
        recursive_scan=recursive_scan,
        max_recursion_depth=max_recursion_depth,
        vector_hit_ids=vector_hit_ids,
        vector_match=vector_match,
        scan_mode=scan_mode,
        scan_external_context=scan_external_context,
        external_context=external_context,
        entry_states=entry_states,
    )
    return explain_preview(
        preview,
        entries,
        hits=list(hit_by_id.values()),
        near_misses=near_misses,
        scope=scope,
        lorebook_id=lorebook_id,
        vector_threshold=effective_threshold,
    )
