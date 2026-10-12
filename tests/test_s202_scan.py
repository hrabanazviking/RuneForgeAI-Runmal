"""S202 acceptance: keyword scanning.

Fixture chats must trigger exactly the expected entries: primary keys,
secondary-key AND semantics, whole-word/case toggles, scan depth,
disabled/constant/empty-key handling, deterministic order.
"""

from runmal.lorebooks.scan import ScanEntry, scan_entries


def e(eid, **kw):
    base = dict(enabled=True, constant=False, keys=(), secondary_keys=(),
                whole_word=True, case_sensitive=False)
    base.update(kw)
    return ScanEntry(id=eid, **base)


def test_primary_key_triggers():
    entries = [e("a", keys=("dragon",))]
    hits = scan_entries(entries, ["hello", "a dragon appears"], 2)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_primary == ("dragon",)
    assert hits[0].message_indices == (1,)


def test_no_match_no_hit():
    entries = [e("a", keys=("dragon",))]
    assert scan_entries(entries, ["hello", "a wyvern appears"], 2) == []


def test_disabled_never_triggers():
    entries = [e("a", enabled=False, keys=("dragon",))]
    assert scan_entries(entries, ["dragon"], 1) == []


def test_constant_skipped_by_scanner():
    # S203 owns constant activation; the scanner must not claim it.
    entries = [e("a", constant=True, keys=("dragon",))]
    assert scan_entries(entries, ["dragon"], 1) == []


def test_empty_keys_never_trigger():
    entries = [e("a", keys=()), e("b", keys=("", "   "))]
    assert scan_entries(entries, ["anything at all"], 1) == []


def test_whole_word_boundary():
    entries = [e("a", keys=("cat",), whole_word=True)]
    assert scan_entries(entries, ["concatenate this"], 1) == []
    assert len(scan_entries(entries, ["the cat sat"], 1)) == 1


def test_substring_when_not_whole_word():
    entries = [e("a", keys=("cat",), whole_word=False)]
    hits = scan_entries(entries, ["concatenate this"], 1)
    assert [h.entry_id for h in hits] == ["a"]


def test_case_sensitive():
    entries = [e("a", keys=("Cat",), case_sensitive=True)]
    assert scan_entries(entries, ["a cat"], 1) == []
    assert len(scan_entries(entries, ["a Cat"], 1)) == 1


def test_case_insensitive_default():
    entries = [e("a", keys=("Cat",))]
    assert len(scan_entries(entries, ["a cat"], 1)) == 1


def test_secondary_keys_require_both():
    entries = [e("a", keys=("dragon",), secondary_keys=("fire",))]
    # primary alone is not enough when secondaries are defined
    assert scan_entries(entries, ["a dragon"], 1) == []
    hits = scan_entries(entries, ["a dragon breathes fire"], 1)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_secondary == ("fire",)


def test_secondary_without_primary_no_trigger():
    entries = [e("a", keys=("dragon",), secondary_keys=("fire",))]
    assert scan_entries(entries, ["fire everywhere"], 1) == []


def test_entry_without_primaries_but_secondaries_no_trigger():
    entries = [e("a", keys=(), secondary_keys=("fire",))]
    assert scan_entries(entries, ["fire"], 1) == []


def test_scan_depth_limits_window():
    entries = [e("a", keys=("dragon",))]
    msgs = ["dragon here", "nothing", "nothing"]
    assert scan_entries(entries, msgs, 2) == []      # key is outside the window
    assert len(scan_entries(entries, msgs, 3)) == 1  # inside the window


def test_scan_depth_one_only_last_message():
    entries = [e("a", keys=("dragon",))]
    assert scan_entries(entries, ["dragon", "nothing"], 1) == []
    hits = scan_entries(entries, ["nothing", "dragon"], 1)
    assert hits[0].message_indices == (1,)


def test_regex_special_keys_match_literally():
    entries = [e("a", keys=("c++",), whole_word=False)]
    assert len(scan_entries(entries, ["i love c++"], 1)) == 1
    assert scan_entries(entries, ["i love cxx"], 1) == []


def test_deterministic_input_order_preserved():
    entries = [e("b", keys=("x",)), e("a", keys=("x",))]
    hits = scan_entries(entries, ["x marks it"], 1)
    assert [h.entry_id for h in hits] == ["b", "a"]


def test_multiple_keys_report_all_matched():
    entries = [e("a", keys=("dragon", "wyvern"))]
    hits = scan_entries(entries, ["dragon and wyvern"], 1)
    assert hits[0].matched_primary == ("dragon", "wyvern")


def test_message_indices_cover_all_matching_messages():
    entries = [e("a", keys=("dragon",))]
    hits = scan_entries(entries, ["dragon one", "nothing", "dragon two"], 3)
    assert hits[0].message_indices == (0, 2)


def test_scan_depth_validation():
    with __import__("pytest").raises(ValueError):
        scan_entries([e("a", keys=("x",))], ["x"], 0)


def test_empty_inputs():
    assert scan_entries([], ["x"], 2) == []
    assert scan_entries([e("a", keys=("x",))], [], 2) == []


def test_from_orm_adapter():
    from runmal.lorebooks.scan import ScanEntry as SE

    class Fake:
        id = "orm-1"
        enabled = 1
        constant = 0
        keys_json = '["dragon"]'
        secondary_keys_json = '["fire"]'
        whole_word = 1
        case_sensitive = 0

    se = SE.from_orm(Fake())
    assert se.id == "orm-1"
    assert se.keys == ("dragon",)
    assert se.secondary_keys == ("fire",)
    hits = scan_entries([se], ["dragon breathes fire"], 1)
    assert [h.entry_id for h in hits] == ["orm-1"]
