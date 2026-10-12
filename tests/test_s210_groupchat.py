"""S210 acceptance: group chat scenario tests with a fake backend.

Multiple personas answer about shared state: mention gating, round-robin
turn taking, broadcast with in-turn shared visibility, and prompt shaping.
"""

from runmal.groupchat.core import GroupChat, Participant, Strategy

PERSONAS = [
    Participant("c-bryn", "Bryn", "Bryn, a skald."),
    Participant("c-una", "Una", "Una, a healer."),
    Participant("c-kol", "Kol", "Kol, a smith."),
]


def fake_backend(participant, prompt):
    """Fake backend: answers about the shared state it was shown."""
    turns = [m for m in prompt if m["role"] != "system"]
    last = turns[-1]["content"] if turns else ""
    return f"{participant.name} saw {len(turns)} turns; last: {last}"


def make_chat():
    return GroupChat(participants=list(PERSONAS))


def test_mention_gating_only_mentioned_speaks():
    chat = make_chat()
    chat.post_user("Hey @Bryn, what of the road ahead?")
    replies = chat.run_turn(fake_backend, Strategy.MENTION)
    assert [r.author for r in replies] == ["Bryn"]
    assert "road ahead" in replies[0].content


def test_mention_gating_no_mention_no_speech():
    chat = make_chat()
    chat.post_user("What does everyone think?")
    replies = chat.run_turn(fake_backend, Strategy.MENTION)
    assert replies == []
    assert len(chat.history) == 1  # only the user's message


def test_mention_multiple_and_case_insensitive():
    chat = make_chat()
    chat.post_user("@una and @KOL, speak!")
    replies = chat.run_turn(fake_backend, Strategy.MENTION)
    assert [r.author for r in replies] == ["Una", "Kol"]  # participant order


def test_mention_prefix_does_not_false_positive():
    chat = make_chat()
    chat.post_user("@Brynhildr, not you Bryn")
    replies = chat.run_turn(fake_backend, Strategy.MENTION)
    assert replies == []


def test_round_robin_rotates():
    chat = make_chat()
    speakers = []
    for i in range(4):
        chat.post_user(f"question {i}")
        replies = chat.run_turn(fake_backend, Strategy.ROUND_ROBIN)
        speakers.extend(r.author for r in replies)
    assert speakers == ["Bryn", "Una", "Kol", "Bryn"]


def test_broadcast_shared_state_visibility():
    chat = make_chat()
    chat.post_user("Tell me of yourselves.")
    replies = chat.run_turn(fake_backend, Strategy.BROADCAST)
    assert [r.author for r in replies] == ["Bryn", "Una", "Kol"]
    # Kol, speaking last, saw both earlier answers in the shared state:
    # prompt turns = user + Bryn + Una = 3 turns before Kol's own answer.
    assert "saw 3 turns" in replies[2].content
    # and Una saw Bryn's answer (labeled) before answering
    assert "saw 2 turns" in replies[1].content


def test_prompt_shaping_per_persona():
    chat = make_chat()
    chat.post_user("hello all")
    chat.run_turn(fake_backend, Strategy.BROADCAST)
    bryn_prompt = chat.build_prompt(PERSONAS[0])
    assert bryn_prompt[0] == {"role": "system", "content": "Bryn, a skald."}
    roles = [(m["role"], m["content"]) for m in bryn_prompt[1:]]
    assert roles[0][0] == "user" and roles[0][1] == "hello all"
    # Bryn's own message is an assistant turn for Bryn...
    assert any(r == "assistant" and "Bryn saw" in c for r, c in roles)
    # ...while for Una, Bryn's message is a labeled user turn
    una_prompt = chat.build_prompt(PERSONAS[1])
    una_contents = [m["content"] for m in una_prompt]
    assert any(c.startswith("Bryn: ") for c in una_contents)


def test_speakers_for_empty_group():
    chat = GroupChat(participants=[])
    chat.post_user("anyone?")
    assert chat.run_turn(fake_backend, Strategy.ROUND_ROBIN) == []
    assert chat.run_turn(fake_backend, Strategy.BROADCAST) == []
