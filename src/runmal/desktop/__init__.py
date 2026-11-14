"""Rúnmál desktop shell (R-04) — native PySide6 windowed application.

This package ``__init__`` deliberately imports nothing Qt-related (and
nothing at all beyond this docstring): the client layer under
``runmal.desktop.client`` must stay importable and testable on hosts
without PySide6 installed. Qt imports live only in the window/worker/
app modules, which are imported explicitly by the entry point.
"""
