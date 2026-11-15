"""Memory-browser logic for the desktop shell (R-12) — Qt-free.

The engine's memory API (S410) is a read surface: list with
search/state/kind filters, and a detail read carrying sources
and the provenance graph. There are no memory write or
embedding routes — embedding is a property of the backend
profile (R-09 Connections). This module holds the browser's
words: list lines, the detail/provenance rendering, and the
honest note about where embedding lives.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import MemoryView, RunmalClient

EMBEDDING_NOTE = (
    "Memories are read here. Which embedding model a connection "
    "uses — and whether memory recall is active — is set per "
    "backend profile in Tools ▸ Connections…; the engine offers "
    "no separate embedding or re-embedding controls."
)


def memory_line(memory: MemoryView) -> str:
    bits = [memory.content.strip().split("\n")[0][:80] or "(empty)"]
    if memory.kind:
        bits.append(memory.kind)
    if memory.state:
        bits.append(memory.state)
    if memory.pinned:
        bits.append("pinned")
    return " · ".join(bits)


def detail_words(detail: dict[str, Any]) -> str:
    """The detail pane: fields, sources, provenance — in words."""
    if not detail:
        return "No memory selected."
    lines: list[str] = [str(detail.get("content", "")).strip()]
    meta: list[str] = []
    for key, label in (
        ("kind", "Kind"),
        ("state", "State"),
        ("scope", "Scope"),
        ("subject", "Subject"),
    ):
        value = detail.get(key)
        if value:
            meta.append(f"{label}: {value}")
    for key, label in (
        ("salience", "Salience"),
        ("stability", "Stability"),
        ("confidence", "Confidence"),
    ):
        value = detail.get(key)
        if isinstance(value, (int, float)):
            meta.append(f"{label}: {value:.2f}")
    if detail.get("pinned"):
        meta.append("Pinned: yes")
    recalls = detail.get("recall_count")
    if isinstance(recalls, int) and recalls:
        meta.append(f"Recalled: {recalls} time(s)")
    witnesses = detail.get("witnesses") or []
    if witnesses:
        meta.append("Witnesses: " + ", ".join(str(w) for w in witnesses))
    if meta:
        lines.append("")
        lines.extend(meta)
    sources = detail.get("sources") or []
    if sources:
        lines.append("")
        lines.append("Sources:")
        for source in sources:
            if not isinstance(source, dict):
                continue
            kind = source.get("kind") or source.get("source_kind") or "source"
            extractor = source.get("extractor") or source.get("extracted_by")
            ref = source.get("ref") or source.get("reference") or ""
            line = f"- {kind}"
            if extractor:
                line += f" · extracted by {extractor}"
            if ref:
                line += f" · {ref}"
            lines.append(line)
    graph = detail.get("graph")
    if isinstance(graph, dict) and graph:
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        lines.append("")
        lines.append(
            f"Provenance graph: {len(nodes)} node(s), {len(edges)} edge(s)."
        )
    return "\n".join(lines)


class MemoryFlow:
    """The Memory dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def search(
        self,
        *,
        q: str = "",
        state: str | None = None,
        kind: str | None = None,
    ) -> list[MemoryView]:
        return self._client.list_memories(q=q, state=state, kind=kind)

    def detail(self, memory_id: str) -> dict[str, Any]:
        return self._client.get_memory(memory_id)
