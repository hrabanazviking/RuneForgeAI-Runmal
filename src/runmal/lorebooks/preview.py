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

Opt-in recursive mode (P-031): with ``recursive_scan=True`` the
preview uses recursive scanning -- keys found in a fired entry's
own content can fire further entries -- and the result gains
recursion metadata. The default (``recursive_scan=False``) path
is unchanged. The scan's token budget bounds recursive expansion;
final inclusion is still decided by the budget/priority pass, so a
directly-hit entry over budget shows as discarded, never as
silently untriggered.
"""

from __future__ import annotations

from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.groups import normalise_group_weight, normalise_inclusion_group
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    ScanEntry,
    scan_entries,
    scan_entries_recursive,
)


def preview_activation(
    entries: list,
    messages: list[str],
    scan_depth: int,
    token_budget: int | None,
    seed: int | None = None,
    *,
    recursive_scan: bool = False,
    max_recursion_depth: int = MAX_RECURSIVE_SCAN_DEPTH,
) -> dict:
    """Preview one activation tick for ``entries`` (ORM rows, service order).

    ``scan_depth`` and ``token_budget`` are the effective values (the caller
    resolves book defaults). Returns a JSON-shaped dict with one row per
    entry plus totals. Row ``status`` is one of ``included`` (activated and
    inside budget), ``discarded`` (activated but dropped by the budget pass,
    with ``discard_reason``), ``not_triggered`` (enabled but not activated
    this tick), ``group_excluded`` (activated but lost its
    inclusion group, P-034), or ``disabled``.
    """
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")

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
        )
        hits = recursive_result.hits
        hit_by_id = {h.entry_id: h for h in hits}
        result = activate(
            act_view,
            set(hit_by_id),
            recursive_hit_ids={h.entry_id for h in hits if h.depth > 0},
            hit_depths={h.entry_id: h.depth for h in hits if h.depth > 0},
        )
    else:
        hits = scan_entries(scan_view, list(messages), scan_depth)
        hit_by_id = {h.entry_id: h for h in hits}
        result = activate(act_view, set(hit_by_id))
    act_by_id = {a.entry_id: a for a in result.activations}
    group_loser_by_id = {row.entry_id: row for row in result.group_losers}
    group_suppressed_by_id = {a.entry_id: a for a in result.group_suppressed}

    candidates = [
        BudgetCandidate(
            entry_id=a.entry_id,
            content=a.content,
            priority=int(by_id[a.entry_id].priority or 0),
        )
        for a in result.activations
    ]
    budget = resolve_budget(candidates, token_budget, seed=seed)
    included = {b.entry_id: b for b in budget.included}
    discarded = {d.entry_id: d for d in budget.discarded}

    rows: list[dict] = []
    for entry in entries:
        entry_id = str(entry.id)
        row: dict = {
            "entry_id": entry_id,
            "name": str(entry.name or ""),
            "enabled": bool(entry.enabled),
            "constant": bool(entry.constant),
            "matched_primary": [],
            "matched_secondary": [],
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
        }
        hit = hit_by_id.get(entry_id)
        if hit is not None:
            row["matched_primary"] = list(hit.matched_primary)
            row["matched_secondary"] = list(hit.matched_secondary)
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
            if entry_id in included:
                row["status"] = "included"
                row["tokens"] = included[entry_id].tokens
            else:
                dropped = discarded[entry_id]
                row["status"] = "discarded"
                row["tokens"] = dropped.tokens
                row["discard_reason"] = dropped.reason
        rows.append(row)

    preview: dict = {
        "scan_depth": scan_depth,
        "token_budget": token_budget,
        "tokens_used": budget.tokens_used,
        "entries": rows,
    }
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
