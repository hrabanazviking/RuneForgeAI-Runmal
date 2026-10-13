"""S808 (roadmap): the sovereign resurrection test — Campaign VIII close.

The whole sovereignty claim in one run: a complete world in state
dir A is exported as a portable archive (S801), imported into a
clean state dir B (S802), its derived indexes are rebuilt under a
DIFFERENT embedding profile (S415), and in B the same persona, chat,
lore, and memory open — statement content and source provenance
intact, embeddings honestly re-declared under the new profile — and
the resurrected world can hold a new conversation through the seam.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from runmal.backends.embeddings import EmbeddingProvenance, FakeEmbeddingBackend
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.chats.service import append_message, get_history
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import (
    Character,
    Chat,
    LoreEntry,
    Memory,
    MemoryChunk,
    Message,
    SamplingPreset,
    User,
)
from runmal.generation.service import generate_events
from runmal.memory import service as memory_service
from runmal.memory.rebuild import rebuild_memory
from runmal.memory.retrieval import RetrievalQuery
from runmal.memory.scope import Viewer, scoped_retrieve
from runmal.memory.vectorstore import InMemoryVectorStore
from runmal.portable.archive import export_archive
from runmal.portable.restore import import_archive

AVATAR = b"\x89PNG\r\n\x1a\nresurrection"
CARD = {"name": "Yrsa", "description": "seidkona of the black fjord"}
PROV_A = EmbeddingProvenance("ollama", "nomic-embed-text", 768, "1")
PROV_B = EmbeddingProvenance("fake", "fake-embed-2", 16, "1")


async def _seed_world_a(tmp_path: Path):
    """A full world in state dir A; returns (archive, ids)."""
    src = tmp_path / "state-a"
    src.mkdir()
    db_path = src / "runmal.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        character = Character(
            user_id=user.id,
            name="Yrsa",
            card_json=json.dumps(CARD),
            avatar_asset="avatar.png",
        )
        session.add(character)
        await session.commit()
        asset_dir = src / "assets" / "characters" / character.id
        asset_dir.mkdir(parents=True)
        (asset_dir / "avatar.png").write_bytes(AVATAR)
        chat = Chat(user_id=user.id, title="hearth", character_id=character.id)
        session.add(chat)
        await session.commit()
        session.add_all(
            [
                Message(chat_id=chat.id, role="user", content="hello"),
                Message(chat_id=chat.id, role="assistant", content="hail"),
            ]
        )
        from runmal.db.models import Lorebook, MemorySource

        book = Lorebook(user_id=user.id, name="sagas")
        session.add(book)
        await session.commit()
        session.add(
            LoreEntry(
                lorebook_id=book.id,
                user_id=user.id,
                keys_json='["odin"]',
                content="All-Father",
            )
        )
        memory = Memory(user_id=user.id, content="Volmarr prefers tea", chat_id=chat.id)
        session.add(memory)
        await session.commit()
        session.add(
            MemorySource(
                memory_id=memory.id,
                source_kind="chat",
                source_id=chat.id,
                chat_id=chat.id,
            )
        )
        session.add(
            MemoryChunk(
                memory_id=memory.id,
                chunk_index=0,
                text="Volmarr prefers tea",
                provider=PROV_A.provider,
                model=PROV_A.model,
                dims=PROV_A.dims,
                version="1",
            )
        )
        session.add(SamplingPreset(user_id=user.id, name="calm", params_json="{}"))
        await session.commit()
        archive = tmp_path / "world.runmal"
        await export_archive(session, user.id, archive, base_dir=src)
        ids = {
            "user": user.id,
            "character": character.id,
            "chat": chat.id,
            "memory": memory.id,
        }
    return archive, ids


async def test_sovereign_resurrection(tmp_path):
    archive, ids = await _seed_world_a(tmp_path)

    # --- Resurrect into a clean state dir B. ---
    dir_b = tmp_path / "state-b"
    report = await import_archive(archive, dir_b)
    assert report.ok
    factory_b = create_session_factory(create_db_engine(Path(report.staged_db)))

    async with factory_b() as session:
        # Persona opens identically.
        character = await session.get(Character, ids["character"])
        assert character is not None and character.name == "Yrsa"
        assert json.loads(character.card_json) == CARD
        # Lore opens identically.
        entry = (await session.scalars(select(LoreEntry))).first()
        assert entry is not None and entry.content == "All-Father"
        # The conversation opens identically.
        history = await get_history(session, ids["user"], ids["chat"])
        assert [m.content for m in history] == ["hello", "hail"]
        # Memory statement + its original embedding provenance arrive.
        memory = await session.get(Memory, ids["memory"])
        assert memory is not None and memory.content == "Volmarr prefers tea"
        chunk = (await session.scalars(select(MemoryChunk))).first()
        assert (chunk.provider, chunk.model, chunk.dims) == (
            PROV_A.provider,
            PROV_A.model,
            PROV_A.dims,
        )
    avatar_b = dir_b / "assets" / "characters" / ids["character"] / "avatar.png"
    assert avatar_b.read_bytes() == AVATAR

    # --- Rebuild derived indexes under a DIFFERENT embedding profile. ---
    backend_b = FakeEmbeddingBackend(dims=16, model="fake-embed-2")
    store = InMemoryVectorStore()
    async with factory_b() as session:
        rebuild = await rebuild_memory(session, ids["user"], backend_b, store)
        await session.commit()
        assert rebuild.provenance == PROV_B.to_dict()
        assert store.count(PROV_B) >= 1
        assert store.count(PROV_A) == 0  # the old space is gone, not mixed

        # The statement survives with its source provenance intact,
        # honestly re-embedded under the new profile.
        memories = await memory_service.list_memories(session, ids["user"])
        tea = [m for m in memories if m.content == "Volmarr prefers tea"]
        assert len(tea) == 1
        sources = await memory_service.list_sources(session, tea[0].id)
        assert sources and sources[0].chat_id == ids["chat"]
        chunks = list(
            await session.scalars(select(MemoryChunk).where(MemoryChunk.memory_id == tea[0].id))
        )
        assert chunks and all(
            (c.provider, c.model, c.dims) == ("fake", "fake-embed-2", 16) for c in chunks
        )
        assert json.loads(tea[0].embedding_json)["model"] == "fake-embed-2"

        # And it is retrievable in the new space.
        hits = await scoped_retrieve(
            session,
            ids["user"],
            Viewer(),
            RetrievalQuery(text="tea"),
            store=store,
            backend=backend_b,
        )
        assert any(h.memory_id == tea[0].id for h in hits)

        # --- The resurrected world holds a NEW conversation. ---
        events = [
            e
            async for e in generate_events(
                "req-808",
                messages=[ChatMessage("user", "are you still yourself?")],
                backend=FakeChatBackend(),
            )
        ]
        tokens = "".join(e["text"] for e in events if e["type"] == "token")
        assert tokens  # generation flowed through the seam in B
        await append_message(
            session,
            ids["user"],
            ids["chat"],
            role="user",
            content="are you still yourself?",
        )
        await append_message(session, ids["user"], ids["chat"], role="assistant", content=tokens)
        await session.commit()
        history = await get_history(session, ids["user"], ids["chat"])
        assert [m.content for m in history][:2] == ["hello", "hail"]
        assert len(history) == 4  # the old world AND the new turn
