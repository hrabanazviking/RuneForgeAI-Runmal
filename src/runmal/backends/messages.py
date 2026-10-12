"""Normalized chat messages (S301). Provider wire shapes never appear here."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    name: str | None = None

    def to_dict(self) -> dict:
        out = {"role": self.role, "content": self.content}
        if self.name is not None:
            out["name"] = self.name
        return out
