"""P-012 acceptance: the clean-room log opened.

The log (docs/CLEAN_ROOM_LOG_2026-10-30.md) is the campaign's
legal-hygiene deliverable: every source consulted per feature
area, in the founding RESEARCH.md pattern, with secondary and
unofficial uses flagged and forbidden sources named. These
tests pin the log's completeness over the banked Part I slices
— every slice P-001..P-011 has an entry, the censuses' exact
source lists are carried, and the open-reading gaps are
recorded — so a future slice must update the log deliberately
instead of the log silently going stale.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"
RESEARCH = REPO / "docs" / "RESEARCH.md"


def _text() -> str:
    return LOG.read_text(encoding="utf-8")


def test_log_exists_and_continues_the_founding_ledger() -> None:
    assert LOG.is_file()
    assert RESEARCH.is_file()
    text = _text()
    assert "docs/RESEARCH.md" in text
    assert "predecessor" in text


def test_forbidden_sources_are_named() -> None:
    text = _text()
    assert "No\n   SillyTavern source code was read" in text or (
        "No SillyTavern source code" in text
    )
    assert "no Voxta source code was read" in text
    assert "source-derived analysis" in text
    # The log does not license copying, and the licence gate binds.
    assert "never reproduced" in text
    assert "no GPL-tainted engine ships" in text


def test_every_part1_slice_has_an_entry() -> None:
    text = _text()
    for slice_id in (
        "P-001", "P-002", "P-003", "P-004", "P-005", "P-006",
        "P-007", "P-008", "P-009", "P-010", "P-011",
    ):
        assert slice_id in text, slice_id
    # Own-tree slices say so explicitly, per the log's own rule.
    assert "no external source" in text
    assert "No new mirror reading" in text or "no new external source" in text


def test_census_source_lists_are_carried_exactly() -> None:
    text = _text()
    # SillyTavern: official docs + 1.13.0 full notes + 1.19 line.
    assert "docs.sillytavern.app" in text
    assert "1.13.0" in text and "1.19" in text
    assert "Writing Extensions" in text
    # Voxta: official site + docs pages + release-note versions.
    assert "voxta.ai" in text and "doc.voxta.ai" in text
    for page in (
        "Scenarios", "Actions &\n  tools", "Memory books",
        "Scripting", "Packages", "HUD & stage",
    ):
        assert page in text, page
    assert "v1.11.0" in text and "v1.9.0" in text and "v1.9.3" in text
    # Voice census: the exact official TTS page.
    assert "docs.sillytavern.app/extensions/tts/" in text


def test_flagged_and_unofficial_uses_are_recorded() -> None:
    text = _text()
    # Voxta's one unofficial corroboration, limited to VX-15.
    assert "voxta.axailotl.ai" in text and "VX-15" in text
    assert "unofficial" in text
    # Voxtral's secondary evidence is flagged, not laundered.
    assert "Voxtral" in text and "CC-BY-NC-4.0" in text
    assert "secondary" in text
    # Interop corpus provenance: authored fresh, nothing scraped.
    assert "authored fresh" in text


def test_open_reading_and_future_entry_protocol_are_recorded() -> None:
    text = _text()
    assert "surveyed-but-not-yet-read" in text
    assert "Surveyed-but-not-enumerated" in text
    assert "Assistant" in text and "Inspector" in text
    # Every future slice appends its entry before banking.
    assert "adds its entry before banking" in text
    assert "never rewritten" in text
    # Aesir is logged as Volmarr's own engine, a different class.
    assert "API_SUPPORT_MATRIX_V1" in text and "1eed9706" in text
    assert "not** a mirror census" in text or "not a mirror census" in text
