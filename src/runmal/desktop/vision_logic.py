"""Vision logic for the desktop shell (R-13) — Qt-free.

The words over the engine's vision surface: the provider truth
(the in-tree providers describe image *facts*; no semantic
caption provider exists, and the engine's note says so
verbatim), description and attachment rows, and watch folders
whose scans ingest new images as chat attachments.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from runmal.desktop.client import (
    RunmalClient,
    VisionAttachmentView,
    VisionAttachOutcome,
    VisionDescriptionView,
    VisionProviderView,
    WatchFolderView,
)


def provider_line(provider: VisionProviderView) -> str:
    bits = [provider.provider_id]
    if provider.model:
        bits.append(provider.model)
    if provider.road:
        bits.append(provider.road)
    if provider.semantic:
        bits.append("semantic")
    bits.append("available" if provider.available else "unavailable")
    if provider.note:
        bits.append(provider.note)
    return " · ".join(bits)


def providers_words(payload: dict[str, Any]) -> str:
    """The providers pane: one line per provider, the engine's
    semantic-caption note verbatim, then the per-backend truth
    about which chat backends declare vision at all."""
    lines: list[str] = []
    providers = payload.get("providers")
    if isinstance(providers, list):
        for row in providers:
            if isinstance(row, VisionProviderView):
                lines.append(provider_line(row))
            elif isinstance(row, dict):
                lines.append(provider_line(VisionProviderView.from_dict(row)))
    note = payload.get("semantic_caption_note")
    if isinstance(note, str) and note:
        lines.append("")
        lines.append(note)
    backends = payload.get("backends")
    if isinstance(backends, list) and backends:
        lines.append("")
        for row in backends:
            if not isinstance(row, dict):
                continue
            declared = "yes" if row.get("vision_declared") else "no"
            lines.append(
                f"{row.get('backend_key', '')} · {row.get('model_id', '')}"
                f" · vision declared: {declared}"
            )
    return "\n".join(lines)


def _dims(view: VisionDescriptionView | VisionAttachmentView) -> str:
    if view.image_width and view.image_height:
        return f"{view.image_width}x{view.image_height}"
    return ""


def description_line(description: VisionDescriptionView) -> str:
    bits: list[str] = []
    if description.created_at:
        bits.append(description.created_at)
    if description.provider_id:
        bits.append(description.provider_id)
    if description.source_kind:
        bits.append(description.source_kind)
    text = " ".join(description.description.split())
    if text:
        bits.append(text[:60])
    return " · ".join(bits)


def description_words(description: VisionDescriptionView) -> str:
    """The detail pane: the full description, then its
    provenance — provider, source, question, image facts."""
    lines: list[str] = [description.description]
    lines.append("")
    provider_bits = [
        b
        for b in (
            description.provider_id,
            description.provider_model,
            description.provider_road,
        )
        if b
    ]
    if provider_bits:
        lines.append("Provider: " + " · ".join(provider_bits))
    source = description.source_kind
    if description.source_ref:
        source = f"{source} {description.source_ref}".strip()
    if source:
        lines.append(f"Source: {source}")
    if description.question:
        lines.append(f"Question: {description.question}")
    facts: list[str] = []
    if description.image_format:
        facts.append(description.image_format)
    dims = _dims(description)
    if dims:
        facts.append(dims)
    if description.image_size:
        facts.append(f"{description.image_size} bytes")
    if facts:
        lines.append("Image: " + " · ".join(facts))
    return "\n".join(lines)


def attachment_line(attachment: VisionAttachmentView) -> str:
    bits = [attachment.filename or "(unnamed)"]
    if attachment.image_format:
        bits.append(attachment.image_format)
    dims = _dims(attachment)
    if dims:
        bits.append(dims)
    if attachment.image_size:
        bits.append(f"{attachment.image_size} bytes")
    if attachment.created_at:
        bits.append(attachment.created_at)
    if attachment.message_id:
        bits.append("on a message")
    return " · ".join(bits)


def watch_line(watch: WatchFolderView) -> str:
    bits = [watch.path or watch.id]
    bits.append("enabled" if watch.enabled else "disabled")
    bits.append("recursive" if watch.recursive else "flat")
    if watch.chat_id:
        bits.append(f"chat {watch.chat_id}")
    return " · ".join(bits)


def scan_report_words(report: dict[str, Any]) -> str:
    """One scan's outcome in words: how much was scanned, what
    landed, what skipped and why, and the descriptions an
    opt-in scan produced."""
    lines: list[str] = []
    scanned = report.get("scanned")
    if isinstance(scanned, int):
        lines.append(f"Scanned: {scanned} file(s).")
    ingested = report.get("ingested")
    if isinstance(ingested, list):
        lines.append(f"Ingested: {len(ingested)} new attachment(s).")
        lines.extend(f"- {item}" for item in ingested)
    skipped = report.get("skipped")
    if isinstance(skipped, list) and skipped:
        lines.append("Skipped:")
        for row in skipped:
            if isinstance(row, dict):
                path = row.get("path") or row.get("source_path") or "?"
                reason = row.get("reason") or ""
                lines.append(f"- {path}: {reason}" if reason else f"- {path}")
            else:
                lines.append(f"- {row}")
    if report.get("truncated"):
        lines.append("The scan was truncated at the file limit.")
    described = report.get("described")
    if isinstance(described, list):
        lines.append(f"Described: {len(described)} image(s).")
        lines.extend(f"- {item}" for item in described)
    return "\n".join(lines)


def ingested_line(row: dict[str, Any]) -> str:
    bits = [str(row.get("source_path", "") or "")]
    size = row.get("size")
    if isinstance(size, int) and size:
        bits.append(f"{size} bytes")
    if row.get("attachment_id"):
        bits.append(f"attachment {row['attachment_id']}")
    if row.get("ingested_at"):
        bits.append(str(row["ingested_at"]))
    return " · ".join(bits)


class VisionFlow:
    """The Vision dialog's verbs over the typed client, plus the
    file helpers that read image bytes off disk."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def providers(self) -> dict[str, Any]:
        return self._client.vision_providers()

    def describe_file(
        self,
        chat_id: str,
        path: str | Path,
        question: str = "",
        provider: str | None = None,
    ) -> VisionDescriptionView:
        image_b64 = base64.b64encode(Path(path).read_bytes()).decode()
        return self._client.describe_image(
            chat_id, image_b64=image_b64, question=question, provider=provider
        )

    def describe_attachment(
        self,
        chat_id: str,
        attachment_id: str,
        question: str = "",
        provider: str | None = None,
    ) -> VisionDescriptionView:
        return self._client.describe_image(
            chat_id,
            attachment_id=attachment_id,
            question=question,
            provider=provider,
        )

    def attach_file(
        self,
        chat_id: str,
        path: str | Path,
        *,
        message_id: str | None = None,
        describe: bool = False,
        question: str = "",
    ) -> VisionAttachOutcome:
        source = Path(path)
        image_b64 = base64.b64encode(source.read_bytes()).decode()
        return self._client.attach_image(
            chat_id,
            source.name,
            image_b64,
            message_id=message_id,
            describe=describe,
            describe_question=question,
        )

    def chat_descriptions(self, chat_id: str) -> list[VisionDescriptionView]:
        return self._client.list_chat_descriptions(chat_id)

    def history(
        self,
        q: str = "",
        *,
        chat_id: str | None = None,
        source_kind: str | None = None,
        provider_road: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._client.vision_history(
            q,
            chat_id=chat_id,
            source_kind=source_kind,
            provider_road=provider_road,
            limit=limit,
            offset=offset,
        )

    def delete_description(self, description_id: str) -> bool:
        return self._client.delete_description(description_id)

    def attachments(self, chat_id: str) -> list[VisionAttachmentView]:
        return self._client.list_attachments(chat_id)

    def thumbnail(
        self, attachment_id: str, max_dim: int | None = None
    ) -> bytes:
        return self._client.attachment_thumbnail(attachment_id, max_dim=max_dim)

    def delete_attachment(self, attachment_id: str) -> dict[str, Any]:
        return self._client.delete_attachment(attachment_id)

    def watch_folders(self, chat_id: str) -> list[WatchFolderView]:
        return self._client.list_watch_folders(chat_id)

    def add_watch_folder(
        self, chat_id: str, path: str, recursive: bool = False
    ) -> WatchFolderView:
        return self._client.create_watch_folder(
            chat_id, path, recursive=recursive
        )

    def update_watch_folder(
        self,
        watch_id: str,
        *,
        enabled: bool | None = None,
        recursive: bool | None = None,
    ) -> WatchFolderView:
        return self._client.update_watch_folder(
            watch_id, enabled=enabled, recursive=recursive
        )

    def delete_watch_folder(self, watch_id: str) -> dict[str, Any]:
        return self._client.delete_watch_folder(watch_id)

    def scan(
        self,
        watch_id: str,
        *,
        describe: bool = False,
        describe_question: str = "",
        describe_provider: str | None = None,
        require_semantic: bool = False,
    ) -> dict[str, Any]:
        return self._client.scan_watch_folder(
            watch_id,
            describe=describe,
            describe_question=describe_question,
            describe_provider=describe_provider,
            require_semantic=require_semantic,
        )

    def ingested(self, watch_id: str) -> list[dict[str, Any]]:
        return self._client.list_watch_ingested(watch_id)
