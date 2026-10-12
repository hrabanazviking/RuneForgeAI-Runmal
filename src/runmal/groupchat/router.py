"""Group chat API (S305): stateless turn endpoint with SSE streaming.

The client holds the roster + transcript; each turn posts them with the
new user text and a strategy. The server rebuilds the S210 GroupChat,
and streams per-participant events: ``typing`` -> ``token``* ->
``message`` per speaker, then ``turn_end`` (with the round-robin cursor
to carry into the next turn). Generation runs through the S108 service
(fake backend today; real backends slot in behind the same seam).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import import_card
from runmal.characters import service as characters
from runmal.db.deps import get_owner_id, get_session
from runmal.generation import service as generation
from runmal.groupchat.core import GroupChat, GroupMessage, Participant, Strategy

router = APIRouter(tags=["group"])


class HistoryIn(BaseModel):
    author: str
    content: str


class TurnIn(BaseModel):
    participant_ids: list[str]
    history: list[HistoryIn] = []
    user_text: str
    strategy: str = "mention"
    rr_cursor: int = 0


async def _load_participants(
    session: AsyncSession, user_id: str, ids: list[str]
) -> list[Participant]:
    participants: list[Participant] = []
    for cid in ids:
        character = await characters.get_character(session, user_id, cid)
        if character is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown participant: {cid}",
            )
        card = import_card(character.card_json.encode(), "card.json")
        persona = card.personality or card.description
        participants.append(
            Participant(character_id=character.id, name=character.name,
                        persona=persona)
        )
    return participants


@router.post("/group/turn")
async def group_turn(
    body: TurnIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        strategy = Strategy(body.strategy)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown strategy: {body.strategy!r}",
        ) from exc
    participants = await _load_participants(session, user_id, body.participant_ids)
    chat = GroupChat(
        participants=participants,
        history=[GroupMessage(h.author, h.content) for h in body.history],
    )
    chat.cursor = body.rr_cursor
    chat.post_user(body.user_text)

    async def sse():
        for speaker in chat.speakers_for(strategy):
            yield _event({"type": "typing", "author": speaker.name})
            prompt = chat.build_prompt(speaker)
            prompt_text = "\n".join(m["content"] for m in prompt)
            text = ""
            request_id = generation.new_request_id()
            async for event in generation.generate_events(request_id, prompt_text):
                if event.get("type") == "token":
                    text += event["text"]
                    yield _event(
                        {"type": "token", "author": speaker.name,
                         "text": event["text"]}
                    )
            chat.history.append(GroupMessage(speaker.name, text))
            chat.note_spoke(strategy, speaker)
            yield _event(
                {"type": "message", "author": speaker.name, "content": text}
            )
        yield _event({"type": "turn_end", "rr_cursor": chat.cursor})

    return StreamingResponse(sse(), media_type="text/event-stream")


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
