"""Definition replace-impact preview (P-140, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-140 slice doc.
What the derivation found missing, and what lands here:

- replace is Part IX's remaining consequential definition
  act with no inspect-before-commit surface. Binding has
  two previews (P-136 definition-side, P-138 chat-scoped)
  and deletion has its delete-impact preview (P-139); a
  PUT replace answers only the new record, after the act.
  Yet a successful replace is permanent for the current
  body: the stored definition and its P-131 import report
  are overwritten, the revision moves by one (P-131), and
  definition history retention has been declined in every
  Part IX weighing, so nothing of the old body survives.
- its consequences differ from deletion's, so P-139's
  surface cannot answer for it: bindings pin their
  revision at bind time (P-132) and are NOT
  re-materialised by a replace — after one, every binding
  pinned at the superseded revision diverges from the
  definition it names, while definition_exists stays
  true — and the definition's organisation row stays
  LIVE against the same id (replace writes only the
  definitions document), never orphaned. No road joined
  those facts to the definition before the act.

This module is the read service behind the preview road.
Every fact is read through the owning slice's own verb —
P-135's list_bindings_for_definition for the bindings,
P-134's organisation_view for the filing — so no second
summary or view law is invented; the pinned split and
the impact counts are read from those answers themselves
so they cannot drift. The one fact no existing verb can
state is whether a persisted organisation row exists at
all (an unorganised definition's view is a computed
default identical in shape to a persisted empty filing),
so the service also reads the organisation store's own
get and names it.

Honesty bounds, stated in every answer:

- the preview is a read of the world as it stands:
  previewing replaces, writes and cascades nothing, and
  the definition named still exists at its named
  revision;
- a successful replace is permanent for the current
  body: no un-replace, no definition history, and the
  record's P-131 import report is overwritten with the
  new body's; P-133's stored-export road is the way to
  keep a file copy first, under its own stated limits;
- replacing does not re-materialise any binding: pinned
  revisions and seeded content stay exactly as landed
  (P-132) — content a binding seeded is the chat's own
  truth — and a chat that wants the new body unbinds
  and binds again as its own act;
- replacing does not touch the organisation store: an
  organisation row, if one exists, stays live against
  this definition's id, unlike deletion, which leaves
  the row orphaned (P-139 / P-134);
- no candidate body is judged here: a refused replace
  body changes nothing (P-131 parses before writing),
  and what a successful new body would plant is
  knowable only once it is stored, through the
  bind-plan previews (P-136 / P-138);
- truth-as-data throughout (P-027): previewing a
  definition's replace impact evaluates no condition,
  plays nothing back and executes nothing it carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import list_bindings_for_definition
from runmal.scenarios.organisation import organisation_view

_NOTE_PREVIEW_ONLY = (
    "this preview is a read of the world as it stands; "
    "previewing has replaced, written and cascaded "
    "nothing, and the definition named above still "
    "exists at the revision named above"
)
_NOTE_PERMANENT_FOR_CURRENT_BODY = (
    "a successful replace is permanent for the current "
    "body: the stored definition and its import report "
    "- its own naming of what the original file "
    "carried, including every unmappable element - are "
    "overwritten, the record moves to the next revision "
    "named above, and there is no un-replace and no "
    "definition history; the stored-export road is the "
    "way to keep a file copy first, under its own "
    "stated limits"
)
_NOTE_NO_REMATERIALISATION = (
    "replacing does not re-materialise any binding: "
    "every binding named here keeps the revision it "
    "pinned when it bound and the content it seeded - "
    "messages and variables are the chats' own truth - "
    "so bindings pinned at the current revision would "
    "afterwards pin a superseded revision, named on "
    "the binding read surface by their pinned revision "
    "beside the definition's new one; a chat that wants "
    "the new body unbinds and binds again as its own act"
)
_NOTE_ORGANISATION_SURVIVES = (
    "replacing does not touch the organisation store: "
    "an organisation row, if one exists, stays live "
    "against this definition's id - tags and favourite "
    "survive a replace exactly as filed - unlike "
    "deletion, which leaves the row orphaned"
)
_NOTE_NO_CANDIDATE_JUDGED = (
    "this preview judges no candidate body: a replace "
    "body the parser refuses changes nothing (the store "
    "parses before writing), and what a successful new "
    "body would plant is knowable only once it is "
    "stored - the bind-plan previews compute from "
    "whatever revision is current when they run"
)


def preview_replace_impact(record, bindings, organisation,
                           live_definition_ids) -> dict:
    """The replace-impact envelope for one stored record.

    ``record`` is a ScenarioDefinition (the router has
    already decided existence and ownership);
    ``bindings`` is a ScenarioBindingStore and
    ``organisation`` a ScenarioOrganisationStore for the
    same owner; ``live_definition_ids`` is the caller's
    live definition id set, exactly as the P-135 roads
    build it. The bindings are P-135's own summaries,
    the organisation section is P-134's own view, the
    pinned split and the impact counts are read from
    those answers themselves, and ``next_revision`` is
    P-131's replace law (a successful replace pins
    exactly the current revision + 1). Pure read:
    writes nothing, replaces nothing, cascades nothing.
    """
    rows = list_bindings_for_definition(
        bindings, record.owner_id, record.id, live_definition_ids)
    pinned_current = sum(
        1 for row in rows
        if row["definition_revision"] == record.revision)
    pinned_older = sum(
        1 for row in rows
        if row["definition_revision"] < record.revision)
    pinned_newer = sum(
        1 for row in rows
        if row["definition_revision"] > record.revision)
    org_record = organisation.get(record.id, record.owner_id)
    return {
        "definition_id": record.id,
        "definition_name": record.name,
        "definition_revision": record.revision,
        "source_format": record.source_format,
        "next_revision": record.revision + 1,
        "bindings": rows,
        "organisation": organisation_view(record, org_record),
        "organisation_row_exists": org_record is not None,
        "impact": {
            "bindings_total": len(rows),
            "bindings_pinned_current": pinned_current,
            "bindings_pinned_older": pinned_older,
            "bindings_pinned_newer": pinned_newer,
            "chats_affected": len(rows),
            "organisation_row_survives": org_record is not None,
        },
        "notes": [
            _NOTE_PREVIEW_ONLY,
            _NOTE_PERMANENT_FOR_CURRENT_BODY,
            _NOTE_NO_REMATERIALISATION,
            _NOTE_ORGANISATION_SURVIVES,
            _NOTE_NO_CANDIDATE_JUDGED,
        ],
    }


__all__ = ["preview_replace_impact"]
