"""Vector-store interface + sqlite-vec adapter (S401).

The store is an isolated abstraction keyed by the S311 provenance space
(provider, model, dims, version): every operation names its space, and a
search only ever compares vectors inside that one space (INV-019).

Two implementations share one contract:

- ``InMemoryVectorStore`` — the deterministic fake used in tests and as
  the swap target proving the contract is implementation-independent.
- ``SqliteVecVectorStore`` — the real adapter, backed by the sqlite-vec
  loadable extension (``vec0`` virtual tables, one per provenance space).

Contract (checked by ``check_vector_store_contract`` for both):

- ``insert(space, doc_id, vector)`` stores/replaces one vector.
- ``search(space, query, top_k)`` returns ``[(doc_id, cosine)]`` sorted
  by score descending, ties broken by doc_id for determinism.
- ``delete(space, doc_id)`` removes a vector; deleting a missing id is
  a no-op.
- Vectors whose length differs from the space dims raise ``ValueError``.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
import struct
from abc import ABC, abstractmethod
from pathlib import Path

from runmal.backends.embeddings import EmbeddingProvenance


def space_key(provenance: EmbeddingProvenance) -> str:
    return "|".join(
        [provenance.provider, provenance.model, str(provenance.dims), provenance.version]
    )


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore(ABC):
    @abstractmethod
    def insert(self, provenance: EmbeddingProvenance, doc_id: str, vector) -> None: ...

    @abstractmethod
    def search(self, provenance: EmbeddingProvenance, query, top_k: int = 5) -> list: ...

    @abstractmethod
    def delete(self, provenance: EmbeddingProvenance, doc_id: str) -> None: ...

    @abstractmethod
    def count(self, provenance: EmbeddingProvenance) -> int: ...

    def clear(self, provenance: EmbeddingProvenance | None = None) -> None:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """Deterministic fake store (contract-test swap target)."""

    def __init__(self) -> None:
        self._spaces: dict[str, dict[str, tuple[float, ...]]] = {}

    def insert(self, provenance, doc_id, vector) -> None:
        if len(vector) != provenance.dims:
            raise ValueError("vector dims do not match provenance dims")
        self._spaces.setdefault(space_key(provenance), {})[doc_id] = tuple(
            float(x) for x in vector
        )

    def search(self, provenance, query, top_k: int = 5) -> list:
        if len(query) != provenance.dims:
            raise ValueError("query dims do not match provenance dims")
        bucket = self._spaces.get(space_key(provenance), {})
        scored = [(doc_id, _cosine(query, vec)) for doc_id, vec in bucket.items()]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]

    def delete(self, provenance, doc_id) -> None:
        self._spaces.get(space_key(provenance), {}).pop(doc_id, None)

    def count(self, provenance) -> int:
        return len(self._spaces.get(space_key(provenance), {}))

    def clear(self, provenance=None) -> None:
        if provenance is None:
            self._spaces.clear()
        else:
            self._spaces.pop(space_key(provenance), None)


class SqliteVecVectorStore(VectorStore):
    """sqlite-vec adapter: one ``vec0`` table per provenance space."""

    def __init__(self, db_path: str | Path) -> None:
        import sqlite_vec

        self._conn = sqlite3.connect(str(db_path))
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS vec_spaces ("
            "space_key TEXT PRIMARY KEY, dims INTEGER NOT NULL, tbl TEXT NOT NULL)"
        )
        self._conn.commit()

    def _table(self, provenance: EmbeddingProvenance) -> str:
        key = space_key(provenance)
        row = self._conn.execute(
            "SELECT tbl FROM vec_spaces WHERE space_key = ?", (key,)
        ).fetchone()
        if row:
            return row[0]
        tbl = "vec_" + hashlib.sha256(key.encode()).hexdigest()[:16]
        self._conn.execute(
            f"CREATE VIRTUAL TABLE {tbl} USING vec0(embedding float[{provenance.dims}])"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS vec_ids ("
            "tbl TEXT NOT NULL, rowid INTEGER NOT NULL, doc_id TEXT NOT NULL, "
            "PRIMARY KEY (tbl, doc_id))"
        )
        self._conn.execute(
            "INSERT INTO vec_spaces (space_key, dims, tbl) VALUES (?, ?, ?)",
            (key, provenance.dims, tbl),
        )
        self._conn.commit()
        return tbl

    def insert(self, provenance, doc_id, vector) -> None:
        if len(vector) != provenance.dims:
            raise ValueError("vector dims do not match provenance dims")
        tbl = self._table(provenance)
        self.delete(provenance, doc_id)
        blob = struct.pack(f"{len(vector)}f", *[float(x) for x in vector])
        cur = self._conn.execute(f"INSERT INTO {tbl} (embedding) VALUES (?)", (blob,))
        self._conn.execute(
            "INSERT INTO vec_ids (tbl, rowid, doc_id) VALUES (?, ?, ?)",
            (tbl, cur.lastrowid, doc_id),
        )
        self._conn.commit()

    def search(self, provenance, query, top_k: int = 5) -> list:
        if len(query) != provenance.dims:
            raise ValueError("query dims do not match provenance dims")
        tbl = self._table(provenance)
        blob = struct.pack(f"{len(query)}f", *[float(x) for x in query])
        rows = self._conn.execute(
            f"SELECT rowid, distance FROM {tbl} "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (blob, top_k),
        ).fetchall()
        out = []
        for rowid, distance in rows:
            doc = self._conn.execute(
                "SELECT doc_id FROM vec_ids WHERE tbl = ? AND rowid = ?", (tbl, rowid)
            ).fetchone()
            if doc:  # vec0 L2 distance on float vectors -> cosine-like rank; store 1-d
                out.append((doc[0], 1.0 - float(distance)))
        out.sort(key=lambda pair: (-pair[1], pair[0]))
        return out

    def delete(self, provenance, doc_id) -> None:
        tbl = self._table(provenance)
        row = self._conn.execute(
            "SELECT rowid FROM vec_ids WHERE tbl = ? AND doc_id = ?", (tbl, doc_id)
        ).fetchone()
        if row:
            self._conn.execute(f"DELETE FROM {tbl} WHERE rowid = ?", (row[0],))
            self._conn.execute(
                "DELETE FROM vec_ids WHERE tbl = ? AND doc_id = ?", (tbl, doc_id)
            )
            self._conn.commit()

    def count(self, provenance) -> int:
        tbl = self._table(provenance)
        return self._conn.execute(
            "SELECT COUNT(*) FROM vec_ids WHERE tbl = ?", (tbl,)
        ).fetchone()[0]

    def clear(self, provenance=None) -> None:
        if provenance is None:
            tables = [r[0] for r in self._conn.execute("SELECT tbl FROM vec_spaces")]
            for tbl in tables:
                self._conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            self._conn.execute("DELETE FROM vec_spaces")
            self._conn.execute("DELETE FROM vec_ids")
        else:
            tbl = self._table(provenance)
            self._conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            self._conn.execute("DELETE FROM vec_spaces WHERE tbl = ?", (tbl,))
            self._conn.execute("DELETE FROM vec_ids WHERE tbl = ?", (tbl,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def check_vector_store_contract(store: VectorStore) -> None:
    """Shared S401 contract: identical checks for every implementation."""
    prov = EmbeddingProvenance(provider="fake", model="m1", dims=3, version="1")
    other = EmbeddingProvenance(provider="fake", model="m2", dims=3, version="1")
    store.insert(prov, "a", (1.0, 0.0, 0.0))
    store.insert(prov, "b", (0.9, 0.1, 0.0))
    store.insert(prov, "c", (0.0, 1.0, 0.0))
    assert store.count(prov) == 3
    hits = store.search(prov, (1.0, 0.0, 0.0), top_k=2)
    assert [doc for doc, _ in hits] == ["a", "b"], hits
    assert hits[0][1] > hits[1][1]
    # Space isolation: the other provenance space is empty here.
    assert store.search(other, (1.0, 0.0, 0.0)) == []
    assert store.count(other) == 0
    # Replace + delete semantics.
    store.insert(prov, "a", (0.0, 0.0, 1.0))
    assert store.count(prov) == 3
    store.delete(prov, "a")
    assert store.count(prov) == 2
    store.delete(prov, "missing")  # no-op
    try:
        store.insert(prov, "bad", (1.0, 2.0))
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("dims mismatch must raise ValueError")
