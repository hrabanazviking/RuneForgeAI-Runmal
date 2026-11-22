"""Library search logic for the desktop shell (R-14) — Qt-free.

One search across the owner's library, fanned out to the search
routes that REALLY exist in the engine:

- ``hub`` — ``GET /api/v1/hub/unified-search`` (P-192): one
  query over hub entry metadata AND verified pack contents,
  merged by entry. Owner-wide; always searched.
- ``workspaces`` — ``GET /api/v1/workspaces/unified-search``
  (P-182): entry names AND file contents over ONE chat's bound
  folder, merged by path. The engine's workspace search is
  chat-scoped by its own law — there is no owner-wide workspace
  search — so this source joins the fan-out only when the
  caller names the chat whose bound folder is meant.
- ``faces`` — NO search route exists. The faces routers are
  presentation, roster and census surfaces only; nothing under
  ``src/runmal/faces/`` accepts a query. Faces is therefore
  never a key in the results: an absent source is the honest
  answer, never an empty list dressed as a searched one.

Both real searches are LITERAL substring searches (the engines'
own law): no fuzzy, semantic, ranked or scored matching exists
in either, and none is faked here. An empty query is refused by
both engines, never treated as match-everything.
"""

from __future__ import annotations

from runmal.desktop.client import LibraryHitView, RunmalClient

#: The sources a fan-out can contain, in display order.
SOURCES = ("hub", "workspaces")


def hit_line(source: str, hit: LibraryHitView) -> str:
    """One hit, one line: title (or file name), kind, how it
    matched, and a short excerpt when the source carries one."""
    bits = [hit.title or hit.id or "(unnamed)"]
    if hit.kind:
        bits.append(hit.kind)
    if hit.matched_by:
        bits.append(f"matched by {hit.matched_by}")
    if hit.occurrences:
        bits.append(f"{hit.occurrences} occurrence(s)")
    if hit.locator and source != "hub":
        bits.append(hit.locator)
    line = " · ".join(bits)
    if hit.excerpt:
        excerpt = " ".join(hit.excerpt.split())
        if len(excerpt) > 80:
            excerpt = excerpt[:79] + "…"
        line += f" — {excerpt}"
    return line


def results_words(results: dict[str, list[LibraryHitView]]) -> str:
    """The results pane: one section per source that was
    searched, with its hit count and lines — or the honest
    no-matches words. Sources absent from the dict were not
    searched and are not mentioned."""
    if not results:
        return "No library sources were searched."
    lines: list[str] = []
    total = 0
    for source in SOURCES:
        if source not in results:
            continue
        hits = results[source]
        total += len(hits)
        lines.append(f"{source}: {len(hits)} hit(s)")
        lines.extend(f"- {hit_line(source, h)}" for h in hits)
    if total == 0:
        lines.append("No matches in the searched sources.")
    return "\n".join(lines)


class LibrarySearchFlow:
    """The Library search dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def search(
        self, query: str, chat_id: str | None = None
    ) -> dict[str, list[LibraryHitView]]:
        """Fan one query out to the real search routes (see the
        module docstring for which sources exist and why):
        ``hub`` always, ``workspaces`` when ``chat_id`` names
        the chat whose bound folder is meant. Faces has no
        search route and is never a key."""
        return self._client.search_library(query, chat_id=chat_id)

    def search_hub(self, query: str) -> list[LibraryHitView]:
        hits, _document = self._client.search_hub(query)
        return hits

    def search_workspaces(
        self, query: str, chat_id: str
    ) -> list[LibraryHitView]:
        hits, _document = self._client.search_workspaces(query, chat_id)
        return hits
