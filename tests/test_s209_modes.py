"""S209 acceptance: generation mode state machine.

Distinct modes (normal/swipe/regenerate/impersonate), candidate
persistence across swipes and regenerates, stable prompt identity under
regenerate, and dict round-trip persistence.
"""

import pytest

from runmal.generation.modes import (
    GenerationSession,
    InvalidTransitionError,
    Mode,
    PromptChangedError,
    State,
    prompt_fingerprint,
)

PROMPT = [
    {"role": "system", "content": "You are Yrsa."},
    {"role": "user", "content": "Tell me of the sea."},
]


def driven_session(mode=Mode.NORMAL, contents=("first",)):
    s = GenerationSession(mode=mode)
    s.compose(PROMPT)
    for text in contents:
        s.begin()
        s.complete(text)
        if text != contents[-1]:
            s.regenerate(PROMPT)
    return s


def test_happy_path_normal_commit():
    s = GenerationSession()
    assert s.state is State.IDLE
    fp = s.compose(PROMPT)
    assert fp == prompt_fingerprint(PROMPT)
    s.begin()
    cand = s.complete("The sea is wide.")
    assert cand.sequence == 0
    role, content = s.commit()
    assert (role, content) == ("assistant", "The sea is wide.")
    assert s.state is State.COMMITTED


def test_impersonate_commits_as_user():
    s = driven_session(mode=Mode.IMPERSONATE, contents=("I walk to the shore.",))
    role, content = s.commit()
    assert role == "user"
    assert content == "I walk to the shore."


def test_candidates_persist_across_regenerate_and_swipe():
    s = driven_session(contents=("v1", "v2", "v3"))
    assert [c.content for c in s.candidates] == ["v1", "v2", "v3"]
    assert [c.sequence for c in s.candidates] == [0, 1, 2]
    assert s.active().content == "v3"
    assert s.swipe(-1) is True and s.active().content == "v2"
    assert s.swipe(-1) is True and s.active().content == "v1"
    assert s.swipe(-1) is False  # clamped at the oldest candidate
    assert s.swipe(2) is True and s.active().content == "v3"
    role, content = s.commit()
    assert (role, content) == ("assistant", "v3")


def test_regenerate_requires_identical_prompt():
    s = driven_session(contents=("v1",))
    changed = PROMPT + [{"role": "user", "content": "and the sky?"}]
    with pytest.raises(PromptChangedError):
        s.regenerate(changed)
    # fingerprint key order does not matter (canonical JSON)
    shuffled = [dict(reversed(list(m.items()))) for m in PROMPT]
    s.regenerate(shuffled)
    assert s.state is State.PROMPT_READY


def test_illegal_transitions_raise():
    s = GenerationSession()
    with pytest.raises(InvalidTransitionError):
        s.begin()  # not composed yet
    with pytest.raises(InvalidTransitionError):
        s.complete("x")
    with pytest.raises(InvalidTransitionError):
        s.swipe(1)
    with pytest.raises(InvalidTransitionError):
        s.commit()
    s.compose(PROMPT)
    with pytest.raises(InvalidTransitionError):
        s.compose(PROMPT)  # already composed
    s.abort()
    assert s.state is State.ABORTED
    with pytest.raises(InvalidTransitionError):
        s.abort()  # terminal


def test_abort_from_generating():
    s = GenerationSession()
    s.compose(PROMPT)
    s.begin()
    s.abort()
    assert s.state is State.ABORTED


def test_round_trip_persistence():
    s = driven_session(contents=("v1", "v2"))
    s.swipe(-1)
    restored = GenerationSession.from_dict(s.to_dict())
    assert restored.to_dict() == s.to_dict()
    assert restored.active().content == "v1"
    assert restored.fingerprint == s.fingerprint
    # and the restored session keeps working
    restored.regenerate(PROMPT)
    restored.begin()
    restored.complete("v3")
    assert restored.commit() == ("assistant", "v3")


def test_fingerprint_stable_and_sensitive():
    assert prompt_fingerprint(PROMPT) == prompt_fingerprint(PROMPT)
    assert prompt_fingerprint(PROMPT) != prompt_fingerprint(
        PROMPT + [{"role": "user", "content": "more"}]
    )
