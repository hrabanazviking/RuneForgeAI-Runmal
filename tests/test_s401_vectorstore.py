"""S401 (roadmap): vector-store interface + sqlite-vec adapter.

Acceptance: insert/search round trip + fake-store swap — the same
contract tests pass against the in-memory fake and the sqlite-vec
adapter, and provenance spaces never mix (INV-019).
"""

from __future__ import annotations

import pytest

from runmal.backends.embeddings import EmbeddingProvenance
from runmal.memory.vectorstore import (
    InMemoryVectorStore,
    SqliteVecVectorStore,
    check_vector_store_contract,
)

PROV = EmbeddingProvenance(provider="fake", model="fake-embed-1", dims=8, version="1")


def test_contract_in_memory_fake():
    check_vector_store_contract(InMemoryVectorStore())


def test_contract_sqlite_vec(tmp_path):
    store = SqliteVecVectorStore(tmp_path / "vec.db")
    try:
        check_vector_store_contract(store)
    finally:
        store.close()


def test_sqlite_vec_round_trip_ranking(tmp_path):
    store = SqliteVecVectorStore(tmp_path / "vec.db")
    try:
        store.insert(PROV, "x", (1.0, 0, 0, 0, 0, 0, 0, 0))
        store.insert(PROV, "y", (0.0, 1.0, 0, 0, 0, 0, 0, 0))
        hits = store.search(PROV, (1.0, 0, 0, 0, 0, 0, 0, 0), top_k=1)
        assert hits[0][0] == "x"
        store.delete(PROV, "x")
        assert store.count(PROV) == 1
    finally:
        store.close()


def test_sqlite_vec_persists_across_reopen(tmp_path):
    path = tmp_path / "vec.db"
    store = SqliteVecVectorStore(path)
    store.insert(PROV, "keep", (0.5,) * 8)
    store.close()
    again = SqliteVecVectorStore(path)
    try:
        assert again.count(PROV) == 1
        assert again.search(PROV, (0.5,) * 8, top_k=1)[0][0] == "keep"
    finally:
        again.close()


def test_dims_mismatch_rejected_by_both(tmp_path):
    store = SqliteVecVectorStore(tmp_path / "vec.db")
    try:
        with pytest.raises(ValueError):
            store.insert(PROV, "bad", (1.0, 2.0))
    finally:
        store.close()
    with pytest.raises(ValueError):
        InMemoryVectorStore().insert(PROV, "bad", (1.0,))
