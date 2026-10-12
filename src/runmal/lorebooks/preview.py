"""Activation preview for the lorebook editor (roadmap S209).

Runs the *same* server pipeline the prompt engine uses -- S202 keyword
scan, S203 activation semantics, S204 budget/priority -- over a book's
stored entries and caller-supplied sample messages, from a clean runtime
state (one tick, no sticky/cooldown/delay carryover). The result explains,
per entry, whether it would be injected and why, so the editor's preview
can never drift from the server activation engine: it *is* the engine,
called with the book's rows.
"""

from __future__ import annotations

from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.scan import ScanEntry, scan_entries


def preview_activation(
    entries: list,
    messages: list[str],
    scan_depth: int,
    token_budget: int | None,
    seed: int | None = None,
) -> dict:
    """Preview one activation tick for ``entries`` (ORM rows, service order).

    ``scan_depth`` and ``token_budget`` are the effective values (the caller
    resolves book defaults). Returns a JSON-shaped dict with one row per
    entry plus totals. Row ``status`` is one of ``included`` (activated and
    inside budget), ``discarded`` (activated but dropped by the budget pass,
    with ``discard_reason``), ``not_triggered`` (enabled but not activated
    this tick), or ``disabled``.
    """
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")

    scan_view = [ScanEntry.from_orm(e) for e in entries]
    act_view = [ActivatableEntry.from_orm(e) for e in entries]
    by_id = {str(e.id): e for e in entries}

    hits = scan_entries(scan_view, list(messages), scan_depth)
    hit_by_id = {h.entry_id: h for h in hits}

    result = activate(act_view, set(hit_by_id))
    act_by_id = {a.entry_id: a for a in result.activations}

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
        }
        hit = hit_by_id.get(entry_id)
        if hit is not None:
            row["matched_primary"] = list(hit.matched_primary)
            row["matched_secondary"] = list(hit.matched_secondary)
        activation = act_by_id.get(entry_id)
        if not entry.enabled:
            row["status"] = "disabled"
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

    return {
        "scan_depth": scan_depth,
        "token_budget": token_budget,
        "tokens_used": budget.tokens_used,
        "entries": rows,
    }
