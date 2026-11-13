"""Definition delete-impact preview (P-139, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-139 slice doc.
What the derivation found missing, and what lands here:

- deletion is Part IX's other irreversible act beside
  binding, and by design it cascades nowhere. P-131's
  DELETE removes exactly one definition record; the
  bindings pointing at it stay in their own store and
  turn stale (P-135 names the staleness only after the
  fact, and the per-definition bindings road itself
  answers 404 once the definition is gone), and the
  definition's organisation row stays in its own store
  as an orphan, filtered at every read (P-134). No road
  joined those facts to the definition while it still
  exists, so an owner could not see what deleting a
  definition would orphan before doing it.

This module is the read service behind the preview
road. Every fact is read through the owning slice's
own verb - P-135's list_bindings_for_definition for
the bindings, P-134's organisation_view for the
filing - so no second summary or view law is invented,
and the counts are read from those answers themselves
so they cannot drift. The one fact no existing verb
can state is whether a persisted organisation row
exists at all (an unorganised definition's view is a
computed default identical in shape to a persisted
empty filing), so the service also reads the
organisation store's own get and names it.

Honesty bounds, stated in every answer:

- the preview is a read of the world as it stands:
  previewing deletes, writes and cascades nothing,
  and the definition named still exists;
- deleting does not cascade into the binding store:
  each binding named would remain and would afterwards
  read definition_exists false on the P-135 surface -
  stale, named, never hidden - and each chat's binding
  can still be removed per chat by unbinding (P-132);
- deleting does not cascade into the organisation
  store: an organisation row, if one exists, would
  remain as an orphan, filtered at every read (P-134);
- content a binding already seeded into a chat is the
  chat's own truth (P-132) and is untouched by deleting
  the definition, exactly as by unbinding;
- deletion is permanent in this design: no undelete,
  no definition history, and the record's P-131 import
  report goes with the record; P-133's stored-export
  road is the way to keep a file copy first, under its
  own stated limits.
- truth-as-data throughout (P-027): previewing a
  definition's delete impact evaluates no condition,
  plays nothing back and executes nothing it carries.
"""

from __future__ import annotations

from runmal.scenarios.binding import list_bindings_for_definition
from runmal.scenarios.organisation import organisation_view

_NOTE_PREVIEW_ONLY = (
    "this preview is a read of the world as it stands; "
    "previewing has deleted, written and cascaded "
    "nothing, and the definition named above still exists"
)
_NOTE_BINDINGS_NO_CASCADE = (
    "deleting a definition does not cascade into the "
    "binding store: every binding named here would "
    "remain as a record and would afterwards read "
    "definition_exists false on the binding read "
    "surface - stale, named, never hidden - and each "
    "chat's binding can still be removed per chat by "
    "unbinding"
)
_NOTE_ORGANISATION_NO_CASCADE = (
    "deleting a definition does not cascade into the "
    "organisation store: an organisation row, if one "
    "exists, would remain as an orphan, filtered at "
    "every read and never surfaced; no road cleans "
    "organisation rows up"
)
_NOTE_SEEDED_CONTENT_KEPT = (
    "content a binding already seeded into a chat - "
    "messages and variables - is the chat's own truth "
    "and is untouched by deleting the definition, "
    "exactly as it is untouched by unbinding"
)
_NOTE_PERMANENT = (
    "deletion is permanent in this design: there is no "
    "undelete and no definition history, and the "
    "record's import report - its own naming of what "
    "the original file carried, including every "
    "unmappable element - goes with the record; the "
    "stored-export road is the way to keep a file copy "
    "first, under its own stated limits"
)


def preview_delete_impact(record, bindings, organisation,
                          live_definition_ids) -> dict:
    """The delete-impact envelope for one stored record.

    ``record`` is a ScenarioDefinition (the router has
    already decided existence and ownership);
    ``bindings`` is a ScenarioBindingStore and
    ``organisation`` a ScenarioOrganisationStore for the
    same owner; ``live_definition_ids`` is the caller's
    live definition id set, exactly as the P-135 roads
    build it. The bindings are P-135's own summaries,
    the organisation section is P-134's own view, and
    the impact counts are read from those answers
    themselves. Pure read: writes nothing, deletes
    nothing, cascades nothing.
    """
    rows = list_bindings_for_definition(
        bindings, record.owner_id, record.id, live_definition_ids)
    org_record = organisation.get(record.id, record.owner_id)
    return {
        "definition_id": record.id,
        "definition_name": record.name,
        "definition_revision": record.revision,
        "source_format": record.source_format,
        "bindings": rows,
        "organisation": organisation_view(record, org_record),
        "organisation_row_exists": org_record is not None,
        "impact": {
            "bindings_orphaned": len(rows),
            "organisation_row_orphaned": org_record is not None,
            "chats_affected": len(rows),
        },
        "notes": [
            _NOTE_PREVIEW_ONLY,
            _NOTE_BINDINGS_NO_CASCADE,
            _NOTE_ORGANISATION_NO_CASCADE,
            _NOTE_SEEDED_CONTENT_KEPT,
            _NOTE_PERMANENT,
        ],
    }


__all__ = ["preview_delete_impact"]
