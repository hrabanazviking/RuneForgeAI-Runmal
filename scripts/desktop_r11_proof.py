"""Desktop proof (R-11): Groups in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the Groups dialog through the window's own controls:

- A two-character room is built in the window from the roster
  checklist; the user speaks in the room.
- A turn per strategy: the in-order strategy cycles the roster
  (Gate Keeper, then Mask Bearer), manual honours the chosen
  speaker; generated replies land in the transcript.
- Roster editors land: member settings (talkativeness, mute),
  a "never" override removing a member from selection, the
  peek, leave/return with presence.
- Room settings (name, strategy, deepening generation mode)
  save through the dialog.
- RESTART the whole app on the same data dir: the room, its
  members, its transcript, its strategy and its deepening
  persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r11_proof.py

Prints one line:  R11_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-11", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}
MASK_CARD = {**CARD, "name": "Mask Bearer"}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULT["checks"][name] = {"ok": bool(ok), "detail": detail}
    return bool(ok)


def wait_until(app, predicate, timeout=25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    app.processEvents()
    return predicate()


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import Qt, qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState

    engine = EngineHandle()
    window = create_window(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING, status.label)
    check(
        "first_run_true_on_fresh",
        snapshot is not None and snapshot.first_run.is_first_run is True,
        snapshot.first_run.label if snapshot else "no snapshot",
    )
    if window._wizard is not None:
        window._wizard.close()
        app.processEvents()
        window._wizard = None

    client = window.client()
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    bearer = client.create_character(dict(MASK_CARD), name="Mask Bearer")
    check("characters_seeded", bool(keeper.id and bearer.id))
    window.refresh_blocking()
    app.processEvents()

    # ---- Build the room in the window.
    dialog = window.open_groups_dialog()
    check("groups_dialog_shown", dialog is not None and dialog.isVisible())
    check(
        "roster_lists_characters",
        dialog.new_roster.count() == 2,
        str(dialog.new_roster.count()),
    )
    dialog.new_name.setText("Gate Watch")
    for i in range(dialog.new_roster.count()):
        dialog.new_roster.item(i).setCheckState(Qt.CheckState.Checked)
    dialog._create()
    app.processEvents()
    group_id = dialog._group.id if dialog._group else ""
    check("room_created_via_dialog", bool(group_id), group_id)
    check(
        "dialog_tracks_room",
        dialog.members_list.count() == 2,
        str(dialog.members_list.count()),
    )

    # ---- Speak, then a turn per strategy.
    dialog.say_field.setText("Who watches the gate tonight?")
    dialog._say()
    check(
        "user_line_in_transcript",
        "You: Who watches the gate tonight?"
        in dialog.transcript.toPlainText(),
    )
    dialog.policy_combo.setCurrentIndex(
        dialog.policy_combo.findData("list")
    )
    dialog._save_settings()
    check(
        "policy_saved",
        client.get_group(group_id).speaker_policy == "list",
        client.get_group(group_id).speaker_policy,
    )
    dialog._next_turn()
    check(
        "first_turn_is_keeper",
        dialog.turn_label.text().startswith("Next speaker: Gate Keeper"),
        dialog.turn_label.text(),
    )
    check(
        "reply_in_transcript",
        "Gate Keeper:" in dialog.transcript.toPlainText(),
        dialog.transcript.toPlainText()[-120:],
    )
    dialog._next_turn()
    check(
        "second_turn_cycles_to_bearer",
        dialog.turn_label.text().startswith("Next speaker: Mask Bearer"),
        dialog.turn_label.text(),
    )
    dialog.run_spin.setValue(2)
    dialog._run_turns()
    check(
        "run_turns_ok",
        dialog.turn_label.text().startswith("Ran 2 turns."),
        dialog.turn_label.text(),
    )
    dialog.policy_combo.setCurrentIndex(
        dialog.policy_combo.findData("manual")
    )
    dialog._save_settings()
    index = dialog.manual_combo.findData(keeper.id)
    dialog.manual_combo.setCurrentIndex(index)
    dialog._next_turn()
    check(
        "manual_pick_honoured",
        dialog.turn_label.text().startswith("Next speaker: Gate Keeper"),
        dialog.turn_label.text(),
    )

    # ---- Roster editors.
    dialog.policy_combo.setCurrentIndex(
        dialog.policy_combo.findData("list")
    )
    dialog._save_settings()
    dialog.members_list.setCurrentRow(1)  # Mask Bearer
    dialog.talk_spin.setValue(0.9)
    dialog._save_member()
    member = next(
        m for m in client.get_group(group_id).members
        if m.character_id == bearer.id
    )
    check(
        "member_settings_saved",
        member.talkativeness == 0.9,
        str(member.talkativeness),
    )
    dialog.members_list.setCurrentRow(0)  # Gate Keeper
    dialog.activation_combo.setCurrentIndex(
        dialog.activation_combo.findData("never")
    )
    dialog._save_override()
    dialog._next_turn()
    check(
        "never_override_skips_keeper",
        dialog.turn_label.text().startswith("Next speaker: Mask Bearer"),
        dialog.turn_label.text(),
    )
    dialog.activation_combo.setCurrentIndex(
        dialog.activation_combo.findData("default")
    )
    dialog._save_override()
    dialog._peek()
    check(
        "peek_shows_persona",
        "persona" in dialog.peek_text.toPlainText().lower(),
        dialog.peek_text.toPlainText()[:80],
    )
    dialog.members_list.setCurrentRow(1)
    dialog._leave()
    records = client.group_presence(group_id)
    away = next(
        (r for r in records if r.get("character_id") == bearer.id), {}
    )
    check("leave_marks_away", away.get("present") is False, str(away))
    dialog._back()
    records = client.group_presence(group_id)
    back = next(
        (r for r in records if r.get("character_id") == bearer.id), {}
    )
    check("return_marks_present", back.get("present") is True, str(back))

    # ---- Room settings: rename + deepening mode.
    dialog.name_field.setText("Night Watch")
    dialog.mode_combo.setCurrentIndex(
        dialog.mode_combo.findData("join")
    )
    dialog._save_settings()
    check(
        "rename_saved",
        client.get_group(group_id).name == "Night Watch",
        client.get_group(group_id).name,
    )
    deep = client.get_group_deepening(group_id)
    check(
        "deepening_mode_saved",
        deep.get("generation_mode") == "join",
        str(deep.get("generation_mode")),
    )
    message_count = client.get_group(group_id).message_count
    dialog.close()

    # ---- Restart: everything persists.
    window.close()
    app.processEvents()
    check(
        "engine_stopped_for_restart",
        wait_until(app, lambda: engine.status().state is EngineState.STOPPED),
        engine.status().label,
    )
    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )
    client2 = window2.client()
    group2 = client2.get_group(group_id)
    check(
        "room_persists",
        group2.name == "Night Watch" and group2.member_count == 2,
        f"{group2.name} · {group2.member_count}",
    )
    check(
        "transcript_persists",
        group2.message_count == message_count and message_count >= 6,
        str(group2.message_count),
    )
    check(
        "strategy_persists",
        group2.speaker_policy == "list",
        group2.speaker_policy,
    )
    check(
        "deepening_persists",
        client2.get_group_deepening(group_id).get("generation_mode")
        == "join",
    )
    dialog2 = window2.open_groups_dialog()
    check(
        "room_reopens_in_dialog",
        dialog2.groups_list.count() == 1
        and "Night Watch" in dialog2.groups_list.item(0).text(),
        dialog2.groups_list.item(0).text()
        if dialog2.groups_list.count() else "empty",
    )
    dialog2.close()

    window2.close()
    app.processEvents()
    check(
        "engine_stopped_on_quit",
        wait_until(
            app, lambda: engine2.status().state is EngineState.STOPPED
        ),
        engine2.status().label,
    )
    import urllib.request

    try:
        urllib.request.urlopen(engine2.base_url + "/healthz", timeout=2)
        healthz_gone = False
    except Exception:
        healthz_gone = True
    check("healthz_gone_after_quit", healthz_gone)

    RESULT["pass"] = all(c["ok"] for c in RESULT["checks"].values())
    print("R11_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
