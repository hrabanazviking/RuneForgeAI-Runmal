"""Bulk library import (P-022): whole-folder card + lorebook import."""

from runmal.library.models import (
    BulkEntry,
    BulkImportReport,
    BulkKind,
    BulkOutcome,
    RefusalCode,
    RepairCode,
    RepairNote,
    SkippedEntry,
)
from runmal.library.service import (
    MAX_DEPTH,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    import_library_folder,
    import_library_uploads,
)

__all__ = [
    "MAX_DEPTH",
    "MAX_FILES",
    "MAX_TOTAL_BYTES",
    "BulkEntry",
    "BulkImportReport",
    "BulkKind",
    "BulkOutcome",
    "RefusalCode",
    "RepairCode",
    "RepairNote",
    "SkippedEntry",
    "import_library_folder",
    "import_library_uploads",
]
