"""Rúnmál web face (W-01, ADR-0012).

A standalone stdlib web shell over the engine's HTTP API: its own
account store and tabbed pages, NO chat state of its own — history
lives in the engine, so every client of the same instance (desktop,
web, agents) sees the same conversations.
"""
