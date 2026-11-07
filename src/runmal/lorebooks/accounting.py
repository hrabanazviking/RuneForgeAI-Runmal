"""P-044 token accounting -- lore's exact prompt cost per turn,
visible before sending.

Pure-domain module: no DB, no I/O. It answers, before anything is
sent to a backend, what lore costs this turn: how many tokens the
included entries spend, how many the discarded entries would have
spent, how much of the lore token budget remains, and -- when the
caller supplies the contents of rows the budget pass never counted
-- what the untriggered entries would cost if they fired.

Where the counts come from (the honesty contract):

- Counts come ONLY from :mod:`runmal.tokens` --
  :func:`estimate_tokens` by default, the very function the budget
  pass (``lorebooks/budget.py``) and the composer
  (``prompt/composer.py`` via ``prompt/slots.py`` ``slot_tokens``)
  spend with. This module never re-implements the heuristic
  locally (no ``len(text) // 4`` here): one counter, one truth,
  so the account can never drift from the spend it reports.
- An optional ``counter`` callable may be supplied, mirroring
  ``compose(counter=...)``: when a counter is supplied every
  count uses it and the account's quality is EXACT; otherwise
  counts are estimates and the quality is ESTIMATED -- the same
  rule as ``PromptManifest.count_quality``.

What the account is derived from:

- :func:`account_from_rows` builds the account from preview rows
  (``lorebooks/preview.py``). Their ``tokens`` were counted by
  the budget pass from the entry content, and for lore that
  number IS the composer spend for the entry: lore slots are
  non-splittable, so the composer's ``slot_text`` for a lore
  slot is exactly the entry ``content`` the budget pass counted.
- Rows the budget pass did not count (not triggered, disabled,
  group-excluded) carry ``tokens=None`` in the preview. The
  caller may supply their ``contents`` (entry id -> content) so
  this module can count their would-be cost with the same
  counter; rows whose contents are not supplied stay uncounted
  and the account says so honestly (see ``untriggered_tokens``).
- :func:`account_from_trace` is the trace-side twin: a pure
  function over an ``inspect_prompt`` trace dict that sums the
  composer's own manifest numbers carried in the trace, so it
  reconciles with the composition by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.tokens import TokenQuality, estimate_tokens

__all__ = [
    "EntryTokenCost",
    "LoreTokenAccount",
    "count_lore_tokens",
    "account_from_rows",
    "account_from_trace",
]


def count_lore_tokens(content: str, counter=None) -> int:
    """Count one lore entry's ``content`` with the shared counter.

    ``counter`` mirrors ``compose(counter=...)``: when supplied it
    is used for the count (and the count is exact); otherwise
    :func:`runmal.tokens.estimate_tokens` is used.
    """
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    return (counter or estimate_tokens)(content)


@dataclass(frozen=True)
class EntryTokenCost:
    """One preview row's token cost.

    ``tokens`` is the counted cost when the row carries one:
    included AND discarded rows both carry their spent / would-be
    count from the budget pass. ``tokens`` is None when the row
    was never counted and no caller-supplied content filled it in.
    ``spent`` is what the entry actually spends this turn:
    ``tokens`` when included, else 0.
    """

    entry_id: str
    status: str
    tokens: int | None
    spent: int
    # From the row's "lorebook_id" / "scope" keys, when present
    # (layered / scoped previews carry them; plain previews may not).
    book_id: str | None = None
    scope: str | None = None

    @property
    def lorebook_id(self) -> str | None:
        """Alias for ``book_id``: the preview row's key name."""
        return self.book_id


@dataclass(frozen=True)
class LoreTokenAccount:
    """Lore's token account for one turn.

    ``tokens_used`` is the spent sum over included entries;
    ``budget_remaining`` is ``token_budget - tokens_used`` when a
    budget applies, else None (kept honest arithmetic: never
    clamped, so a negative remainder exposes a caller whose rows
    do not match the budget it claims). ``by_status`` maps each
    row status to ``{"count", "tokens", "spent"}`` (tokens sums
    counted tokens only, uncounted rows contributing 0);
    ``by_book`` maps each lorebook id present on the rows to
    ``{"tokens_used", "entries"}``. ``discarded_tokens`` is the
    would-be cost of the budget pass's discards.
    ``untriggered_tokens`` is the would-be cost of the rows that
    did not fire (not_triggered / disabled / group_excluded):
    None when the caller supplied no ``contents`` at all --
    honestly uncounted -- otherwise the counted sum, where a row
    whose id is missing from ``contents`` stays uncounted and
    contributes 0.
    """

    tokens_used: int
    token_budget: int | None
    budget_remaining: int | None
    count_quality: TokenQuality
    entries: tuple[EntryTokenCost, ...]
    by_status: dict
    by_book: dict
    discarded_tokens: int
    untriggered_tokens: int | None

    def to_dict(self) -> dict:
        """Serialize to plain JSON-shaped data."""
        quality = self.count_quality
        return {
            "tokens_used": self.tokens_used,
            "token_budget": self.token_budget,
            "budget_remaining": self.budget_remaining,
            "count_quality": (
                quality.value if isinstance(quality, TokenQuality) else quality
            ),
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "status": entry.status,
                    "tokens": entry.tokens,
                    "spent": entry.spent,
                    "lorebook_id": entry.book_id,
                    "scope": entry.scope,
                }
                for entry in self.entries
            ],
            "by_status": {
                status: dict(summary)
                for status, summary in self.by_status.items()
            },
            "by_book": {
                book_id: dict(summary)
                for book_id, summary in self.by_book.items()
            },
            "discarded_tokens": self.discarded_tokens,
            "untriggered_tokens": self.untriggered_tokens,
        }


#: Statuses whose rows did not fire this turn; their tokens are a
#: would-be cost, never a spend.
_UNTRIGGERED_STATUSES = frozenset({"not_triggered", "disabled", "group_excluded"})


def account_from_rows(
    rows: list[dict],
    *,
    token_budget: int | None,
    counter=None,
    contents: dict[str, str] | None = None,
) -> LoreTokenAccount:
    """Build the token account from preview ``rows``.

    Each row is a preview row dict (``entry_id``, ``status`` and,
    when the budget pass counted it, ``tokens``; scoped rows may
    also carry ``lorebook_id`` and ``scope``).

    A row with ``tokens=None`` is filled in from ``contents``
    (entry id -> content) when the caller supplies it, counted
    with ``counter`` or the shared estimator. An included row
    must always carry a count -- from the budget pass or from
    ``contents`` -- because the account must never silently
    under-report spend: an included row with no count raises
    ``ValueError``.

    ``contents`` also decides ``untriggered_tokens`` honesty:
    with no ``contents`` it is None (uncounted); with ``contents``
    it is the sum over the not_triggered / disabled /
    group_excluded rows after the fill-in, where a row whose id
    is missing from ``contents`` stays uncounted (``tokens``
    remains None on its entry) and contributes 0 to the sum.
    """
    if token_budget is not None and token_budget < 0:
        raise ValueError("token_budget must be >= 0 or None")

    entries: list[EntryTokenCost] = []
    by_status: dict = {}
    by_book: dict = {}
    tokens_used = 0
    discarded_tokens = 0
    untriggered_sum = 0

    for row in rows:
        entry_id = row["entry_id"]
        status = row["status"]
        tokens = row.get("tokens")
        if tokens is None and contents is not None and entry_id in contents:
            tokens = count_lore_tokens(contents[entry_id], counter)
        if status == "included" and tokens is None:
            raise ValueError("included row without a token count")
        spent = tokens if status == "included" and tokens is not None else 0

        book_id = row.get("lorebook_id")
        cost = EntryTokenCost(
            entry_id=entry_id,
            status=status,
            tokens=tokens,
            spent=spent,
            book_id=book_id,
            scope=row.get("scope"),
        )
        entries.append(cost)

        tokens_used += spent
        if status == "discarded":
            discarded_tokens += tokens or 0
        if status in _UNTRIGGERED_STATUSES:
            untriggered_sum += tokens or 0

        status_summary = by_status.setdefault(
            status, {"count": 0, "tokens": 0, "spent": 0}
        )
        status_summary["count"] += 1
        status_summary["tokens"] += tokens or 0
        status_summary["spent"] += spent

        if book_id is not None:
            book_summary = by_book.setdefault(
                book_id, {"tokens_used": 0, "entries": 0}
            )
            book_summary["tokens_used"] += spent
            book_summary["entries"] += 1

    return LoreTokenAccount(
        tokens_used=tokens_used,
        token_budget=token_budget,
        budget_remaining=(
            token_budget - tokens_used if token_budget is not None else None
        ),
        count_quality=(
            TokenQuality.EXACT if counter is not None else TokenQuality.ESTIMATED
        ),
        entries=tuple(entries),
        by_status=by_status,
        by_book=by_book,
        discarded_tokens=discarded_tokens,
        untriggered_tokens=None if contents is None else untriggered_sum,
    )


#: Slot kinds that are lore in a prompt trace (trace.py's LORE_KINDS).
_LORE_KINDS = frozenset({"lore_before", "lore_after"})


def account_from_trace(trace: dict) -> dict:
    """Lore's share of one composed prompt, from its trace dict.

    Pure function over an ``inspect_prompt`` trace dict (the
    ``trace_to_dict`` shape). It counts nothing itself: it sums
    the composer's own manifest numbers carried in the trace, so
    the account reconciles with the composition by construction.

    Lore slots are the trace slots whose kind is ``lore_before``
    or ``lore_after``. ``tokens_used`` sums the included lore
    slots, ``discarded_tokens`` the discarded ones, and the two
    shares place lore inside the whole prompt: ``share_of_input``
    against the ledger's total input tokens, ``share_of_budget``
    against its input budget (both 0.0 when the denominator is
    not positive). ``by_provenance`` groups the same sums by each
    slot's provenance label, with an entry count per provenance.
    """
    ledger = trace["ledger"]
    lore_slots = [s for s in trace["slots"] if s["kind"] in _LORE_KINDS]

    tokens_used = sum(
        s["tokens"] for s in lore_slots if s["status"] == "included"
    )
    discarded_tokens = sum(
        s["tokens"] for s in lore_slots if s["status"] == "discarded"
    )
    total_input_tokens = ledger["total_input_tokens"]
    input_budget = ledger["input_budget"]

    by_provenance: dict = {}
    entries: list[dict] = []
    for slot in lore_slots:
        provenance = slot.get("provenance", "")
        summary = by_provenance.setdefault(
            provenance,
            {"tokens_used": 0, "discarded_tokens": 0, "entries": 0},
        )
        summary["entries"] += 1
        if slot["status"] == "included":
            summary["tokens_used"] += slot["tokens"]
        elif slot["status"] == "discarded":
            summary["discarded_tokens"] += slot["tokens"]
        entries.append(
            {
                "slot_id": slot["slot_id"],
                "tokens": slot["tokens"],
                "status": slot["status"],
                "provenance": provenance,
                "trigger": slot.get("trigger"),
            }
        )

    return {
        "tokens_used": tokens_used,
        "discarded_tokens": discarded_tokens,
        "total_input_tokens": total_input_tokens,
        "input_budget": input_budget,
        "remaining_input_tokens": ledger["remaining_input_tokens"],
        "share_of_input": (
            tokens_used / total_input_tokens if total_input_tokens else 0.0
        ),
        "share_of_budget": (
            tokens_used / input_budget if input_budget else 0.0
        ),
        "count_quality": ledger["count_quality"],
        "by_provenance": by_provenance,
        "entries": entries,
    }
