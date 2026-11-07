"""Activation preview for the lorebook editor (roadmap S209).

Runs the *same* server pipeline the prompt engine uses -- S202 keyword
scan, S203 activation semantics, S204 budget/priority -- over a book's
stored entries and caller-supplied sample messages, from a clean runtime
state (one tick, no sticky/cooldown/delay carryover). The result explains,
per entry, whether it would be injected and why, so the editor's preview
can never drift from the server activation engine: it *is* the engine,
called with the book's rows.

Inclusion groups (P-034): grouped entries that lose their group
show as ``group_excluded`` -- a status of their own, NOT the
budget pass's ``discarded`` (whose ``discard_reason`` vocabulary
is S204's alone: ``over_budget`` / ``probability_skip``). Their
row keeps the ``via`` they fired with, carries
``group_winner_id`` (who won their group), and their
``discard_reason`` stays None. Every row also reports
``inclusion_group`` and ``group_weight``. When any contested
group resolved, the result gains ``inclusion_group_winners``
(group label -> winner entry id). The prompt inspector maps any
non-included status to its trace reason generically, so
group-excluded entries surface there as ``group_excluded`` with
no inspector change.

Probability & RNG honesty (P-036): candidates finally carry the
stored entry probability (percent -> fraction), so the preview
gate is live -- pre-P-036 the preview built candidates with the
default probability 1.0 and the gate never fired here. Every
gated entry's row reports ``probability`` (percent) and
``probability_roll`` (the inspectable roll record: seed,
context, roll value, passed, seeded) or None when ungated; the
result reports ``seed``, ``roll_context`` and
``probability_rolls`` (every gated roll this tick, in budget
processing order). With the same seed + roll_context the
preview reproduces roll-for-roll; with ``seed=None`` the rolls
are recorded with ``seeded: False`` -- inspectable after the
fact, honestly not reproducible.

Opt-in recursive mode (P-031): with ``recursive_scan=True`` the
preview uses recursive scanning -- keys found in a fired entry's
own content can fire further entries -- and the result gains
recursion metadata. The default (``recursive_scan=False``) path
is unchanged. The scan's token budget bounds recursive expansion;
final inclusion is still decided by the budget/priority pass, so a
directly-hit entry over budget shows as discarded, never as
silently untriggered.

Scan windows (P-037): the scan runs over the window the
book's settings resolve (``scan_mode`` / ``scan_depth`` /
``scan_external_context``, caller-resolved like scan_depth);
``external_context`` carries the caller's external texts. The
result reports ``scan_mode``, ``scan_external_context`` and a
``scan_window`` summary (texts scanned, split chat/external --
counts only, never the text), and each hit row reports
``external_indices`` (which external texts its keys matched;
empty when the match was chat-side or there was no hit).
Position & depth control (P-038): every row reports the
entry's declared ``position`` plus its EFFECTIVE placement --
``role`` and ``injection_depth`` from placement_for applied to
the stored position/depth/role triple (before/after: role
system, injection_depth None; at_depth: the stored role and
depth, with the default depth 4 materialised when undeclared).
``injection_depth`` is deliberately not named ``depth``: the
row's existing ``depth`` key is the recursion depth (P-031).
Placement is data only here -- preview does not reorder or
splice content; the composer honours it (prompt/inspect.py
builds the slots from these fields).

Entry states (P-035): vector-fired rows honestly report
``matched_primary`` / ``matched_secondary`` empty (no keyword
matched) with ``via="vector"``; the caller supplies
``vector_hit_ids`` (the embedding matcher is P-041). Every row
also reports ``vectorised`` and the derived ``activation_kind``.

Token account (P-044): every preview carries ``token_account`` --
the per-turn lore cost, visible before sending because preview
never sends. It is built from the final rows via
``account_from_rows``: its ``tokens_used`` equals the sum of the
included rows and equals ``budget.tokens_used``, with
``by_status`` / ``by_book`` breakdowns. Untriggered would-be
costs are counted from stored content with the same counter
(see ``preview_activation`` for the counter recount rule).
"""

from __future__ import annotations

from runmal.lorebooks.accounting import account_from_rows, count_lore_tokens
from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.groups import normalise_group_weight, normalise_inclusion_group
from runmal.lorebooks.placement import (
    normalise_depth,
    normalise_position,
    normalise_role,
    placement_for,
)
from runmal.lorebooks.rng import normalise_probability
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    ScanEntry,
    scan_entries_recursive,
    scan_entries_windowed,
)
from runmal.lorebooks.states import activation_kind_for, normalise_vectorised
from runmal.lorebooks.vector_match import match_vectorised_sync
from runmal.lorebooks.windows import ScanSettings, build_scan_window


def preview_activation(
    entries: list,
    messages: list[str],
    scan_depth: int,
    token_budget: int | None,
    seed: int | None = None,
    *,
    counter=None,
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
) -> dict:
    """Preview one activation tick for ``entries`` (ORM rows, service order).

    ``scan_depth`` and ``token_budget`` are the effective values (the caller
    resolves book defaults). Returns a JSON-shaped dict with one row per
    entry plus totals. Row ``status`` is one of ``included`` (activated and
    inside budget), ``discarded`` (activated but dropped by the budget pass,
    with ``discard_reason``), ``not_triggered`` (enabled but not activated
    this tick), ``group_excluded`` (activated but lost its
    inclusion group, P-034), or ``disabled``.

    ``vector_hit_ids`` (P-035): ids of vectorised entries hit by
    vector matching, supplied by the caller (the embedding matcher
    is P-041). Vector-fired rows honestly report
    ``matched_primary`` / ``matched_secondary`` empty (no keyword
    matched), with ``via="vector"``.

    Vectorised lore (P-041): the matcher is live here now. When
    the caller supplies neither ``vector_hit_ids`` nor a computed
    ``vector_match`` outcome, ``vector_embedder`` (a sync callable
    taking a text list and returning an EmbeddingResult or vector
    sequence -- ``LocalEmbeddingBackend.embed_sync`` is the
    built-in) runs the matcher over this tick's window, honouring
    ``vector_threshold`` / ``vector_max_entries``. Async callers
    precompute the outcome with ``match_vectorised`` and pass it
    as ``vector_match``. Either way the result gains a
    ``vector_match`` summary (mode, degraded, fallback reason,
    provenance, ranked scores, cap count) when the book holds
    vectorised candidates, every row gains ``vector_score`` (the
    candidate's cosine, or None), and keyword-fallback rows report
    their real matched keys with ``via="vector_fallback"``.

    Token account (P-044): with a ``counter``, the account
    recounts every entry with that counter (the same counter
    ``compose(counter=...)`` would spend with); the budget pass
    itself still resolved with the canonical estimator, so
    ``row["tokens"]`` keeps the budget-pass numbers and only
    ``token_account`` reflects the counter. Without a counter,
    the account derives purely from row tokens plus
    estimate-based would-be counts for untriggered rows
    (contents fill) -- quality ESTIMATED.
    """
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")

    # P-037: the effective scan window, from the caller's resolved
    # settings (None means the pre-P-037 defaults: depth mode,
    # external context off).
    settings = ScanSettings.normalised(
        scan_depth=scan_depth,
        scan_mode=scan_mode,
        scan_external_context=scan_external_context,
    )
    external_texts = list(external_context or ())
    window = build_scan_window(settings, list(messages), external_texts)

    # P-041: run the embedding matcher when nobody supplied hits.
    # A caller-supplied vector_match outcome (async live paths)
    # wins over the sync embedder; explicit vector_hit_ids (the
    # P-035 seam) win over both and leave the summary absent,
    # exactly the pre-P-041 shape.
    vector_fallback_ids: set[str] | None = None
    if vector_match is not None:
        if vector_hit_ids is None:
            vector_hit_ids = set(vector_match.hit_ids)
        vector_fallback_ids = set(vector_match.fallback_ids)
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
        vector_fallback_ids = set(vector_match.fallback_ids)
    if vector_match is not None and not vector_match.candidates:
        vector_match = None

    scan_view = [ScanEntry.from_orm(e) for e in entries]
    act_view = [ActivatableEntry.from_orm(e) for e in entries]
    by_id = {str(e.id): e for e in entries}

    recursive_result = None
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
        hits = recursive_result.hits
        hit_by_id = {h.entry_id: h for h in hits}
        result = activate(
            act_view,
            set(hit_by_id),
            recursive_hit_ids={h.entry_id for h in hits if h.depth > 0},
            hit_depths={h.entry_id: h.depth for h in hits if h.depth > 0},
            vector_hit_ids=vector_hit_ids,
            vector_fallback_ids=vector_fallback_ids,
        )
    else:
        hits = scan_entries_windowed(
            scan_view, list(messages), settings, external_texts
        )
        hit_by_id = {h.entry_id: h for h in hits}
        result = activate(
            act_view,
            set(hit_by_id),
            vector_hit_ids=vector_hit_ids,
            vector_fallback_ids=vector_fallback_ids,
        )
    if vector_match is not None:
        # Keyword-fallback hits carry real matched keys; report
        # them on the row like any keyword hit (the row's via
        # stays "vector_fallback" -- the keys are provenance,
        # not a disguise).
        for fb_hit in vector_match.keyword_hits:
            hit_by_id.setdefault(fb_hit.entry_id, fb_hit)
    act_by_id = {a.entry_id: a for a in result.activations}
    group_loser_by_id = {row.entry_id: row for row in result.group_losers}
    group_suppressed_by_id = {a.entry_id: a for a in result.group_suppressed}

    candidates = [
        BudgetCandidate(
            entry_id=a.entry_id,
            content=a.content,
            priority=int(by_id[a.entry_id].priority or 0),
            probability=normalise_probability(
                getattr(by_id[a.entry_id], "probability", None)
            )
            / 100.0,
        )
        for a in result.activations
    ]
    budget = resolve_budget(candidates, token_budget, seed=seed, context=roll_context)
    roll_by_id = {r.entry_id: r for r in budget.rolls}
    included = {b.entry_id: b for b in budget.included}
    discarded = {d.entry_id: d for d in budget.discarded}

    rows: list[dict] = []
    for entry in entries:
        entry_id = str(entry.id)
        placement = placement_for(
            normalise_position(getattr(entry, "position", None)),
            normalise_depth(getattr(entry, "depth", None)),
            normalise_role(getattr(entry, "role", None)),
        )
        vectorised = normalise_vectorised(getattr(entry, "vectorised", None))
        row: dict = {
            "entry_id": entry_id,
            "name": str(entry.name or ""),
            "enabled": bool(entry.enabled),
            "constant": bool(entry.constant),
            "vectorised": vectorised,
            "activation_kind": activation_kind_for(bool(entry.constant), vectorised),
            "matched_primary": [],
            "matched_secondary": [],
            "vector_score": (
                vector_match.scores.get(entry_id) if vector_match is not None else None
            ),
            "external_indices": [],
            "via": None,
            "depth": None,
            "content": None,
            "tokens": None,
            "discard_reason": None,
            "inclusion_group": normalise_inclusion_group(
                getattr(entry, "inclusion_group", None)
            ),
            "group_weight": normalise_group_weight(
                getattr(entry, "group_weight", None)
            ),
            "group_winner_id": None,
            "probability": normalise_probability(getattr(entry, "probability", None)),
            "probability_roll": None,
            "position": normalise_position(getattr(entry, "position", None)),
            "role": placement.role,
            "injection_depth": placement.depth,
        }
        hit = hit_by_id.get(entry_id)
        if hit is not None:
            row["matched_primary"] = list(hit.matched_primary)
            row["matched_secondary"] = list(hit.matched_secondary)
            row["external_indices"] = list(hit.external_indices)
        activation = act_by_id.get(entry_id)
        if not entry.enabled:
            row["status"] = "disabled"
        elif entry_id in group_loser_by_id:
            loser = group_loser_by_id[entry_id]
            suppressed = group_suppressed_by_id.get(entry_id)
            row["status"] = "group_excluded"
            row["group_winner_id"] = loser.winner_id
            if suppressed is not None:
                row["via"] = suppressed.via
                row["depth"] = suppressed.depth
        elif activation is None:
            row["status"] = "not_triggered"
        else:
            row["via"] = activation.via
            row["depth"] = activation.depth
            row["content"] = activation.content
            roll = roll_by_id.get(entry_id)
            if roll is not None:
                row["probability_roll"] = roll.to_dict()
            if entry_id in included:
                row["status"] = "included"
                row["tokens"] = included[entry_id].tokens
            else:
                dropped = discarded[entry_id]
                row["status"] = "discarded"
                row["tokens"] = dropped.tokens
                row["discard_reason"] = dropped.reason
        rows.append(row)

    contents = {str(e.id): str(e.content or "") for e in entries}
    if counter is not None:
        account_rows = [
            dict(r, tokens=count_lore_tokens(contents[r["entry_id"]], counter))
            if r["entry_id"] in contents
            else r
            for r in rows
        ]
        account = account_from_rows(
            account_rows, token_budget=token_budget, counter=counter, contents=contents
        )
    else:
        account = account_from_rows(
            rows, token_budget=token_budget, counter=counter, contents=contents
        )

    preview: dict = {
        "scan_depth": scan_depth,
        "scan_mode": settings.scan_mode,
        "scan_external_context": settings.scan_external_context,
        "scan_window": window.summary(),
        "token_budget": token_budget,
        "tokens_used": budget.tokens_used,
        "seed": seed,
        "roll_context": roll_context,
        "entries": rows,
        "token_account": account.to_dict(),
    }
    if vector_match is not None:
        preview["vector_match"] = vector_match.to_dict()
    if budget.rolls:
        preview["probability_rolls"] = [r.to_dict() for r in budget.rolls]
    if group_loser_by_id:
        preview["inclusion_group_winners"] = {
            row.inclusion_group: row.winner_id for row in result.group_losers
        }
    if recursive_scan:
        assert recursive_result is not None
        preview["recursive_scan"] = True
        preview["max_recursion_depth"] = max_recursion_depth
        preview["recursion_depth_reached"] = recursive_result.depth_reached
        preview["recursion_budget_exhausted"] = recursive_result.budget_exhausted
    return preview
