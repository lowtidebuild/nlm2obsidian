"""Import orchestration for NotebookLM → Obsidian.

Routes each content type to the correct handler, writes files,
and updates sync state. All API calls go through notebooklm-py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from .formatters import (
    format_inbox_note,
    format_literature_note,
    format_resource_note,
    mindmap_to_markdown,
    sanitize_filename,
)
from .raw_parser import (
    extract_flashcard_content,
    extract_quiz_content,
    extract_report_text,
    find_content_string,
    log_discovery,
)
from .sync_state import SyncState

logger = logging.getLogger(__name__)

# StudioContentType integer values from notebooklm-py
_TYPE_AUDIO = 1
_TYPE_REPORT = 2
_TYPE_VIDEO = 3
_TYPE_QUIZ_FLASHCARD = 4
_TYPE_MIND_MAP = 5
_TYPE_INFOGRAPHIC = 7
_TYPE_SLIDE_DECK = 8
_TYPE_DATA_TABLE = 9

_STATUS_COMPLETED = 3


@dataclass
class ImportResult:
    """Counts and failure details for an import run."""

    imported: int = 0
    skipped: int = 0
    failed: int = 0
    failures: List[dict] = field(default_factory=list)

    def merge(self, other: "ImportResult") -> None:
        self.imported += other.imported
        self.skipped += other.skipped
        self.failed += other.failed
        self.failures.extend(other.failures)


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


async def import_notebook(
    client: Any,
    notebook: Any,
    vault_path: Path,
    content_types: List[str],
    sync_state: SyncState,
    include_media: bool,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    """Import all requested content types from one notebook."""
    result = ImportResult()
    nb_id = notebook.id
    nb_title = notebook.title

    if "sources" in content_types or "all" in content_types:
        r = await _import_sources(client, nb_id, nb_title, vault_path, sync_state, dry_run, force, verbose)
        result.merge(r)

    if "artifacts" in content_types or "all" in content_types:
        r = await _import_artifacts(client, nb_id, nb_title, vault_path, sync_state, include_media, dry_run, force, verbose)
        result.merge(r)

    if "notes" in content_types or "all" in content_types:
        r = await _import_notes(client, nb_id, nb_title, vault_path, sync_state, dry_run, force, verbose)
        result.merge(r)
        r = await _import_chat_history(client, nb_id, nb_title, vault_path, sync_state, dry_run, force, verbose)
        result.merge(r)

    if not dry_run:
        sync_state.save()

    return result


# ------------------------------------------------------------------
# Sources → Literature notes via get_guide()
# ------------------------------------------------------------------


async def _import_sources(
    client: Any,
    nb_id: str,
    nb_title: str,
    vault_path: Path,
    sync_state: SyncState,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    result = ImportResult()
    nb_dir = sanitize_filename(nb_title)

    try:
        sources = await client.sources.list(nb_id)
    except Exception as e:
        logger.error("Failed to list sources: %s", e)
        result.failed += 1
        result.failures.append({"title": "Source listing", "type": "source", "error": str(e)})
        return result

    for source in sources:
        sid = source.id
        title = source.title or f"Source {sid[:8]}"

        if not force and sync_state.is_synced(nb_id, "sources", sid):
            result.skipped += 1
            if verbose:
                logger.info("  [skip] Source: %s (already synced)", title)
            continue

        try:
            guide = await client.sources.get_guide(nb_id, sid)
            await asyncio.sleep(1)  # rate limit

            summary = guide.get("summary", "")
            keywords = guide.get("keywords", [])

            content = summary
            if keywords:
                content += "\n\n---\n**Keywords:** " + ", ".join(keywords)

            source_type = getattr(source, "source_type", "NotebookLM")
            md = format_literature_note(
                title=title,
                content=content,
                notebook_title=nb_title,
                source_type=source_type,
                author="NotebookLM AI Summary",
            )

            rel_path = f"5. Zettelkasten/10. Literature/NotebookLM/{nb_dir}/{sanitize_filename(title)}.md"

            if dry_run:
                logger.info("  [dry-run] %s", rel_path)
            else:
                write_note(vault_path, rel_path, md)
                sync_state.mark_synced(nb_id, nb_title, "sources", sid, title, rel_path)

            result.imported += 1
            if verbose:
                logger.info("  [import] Source: %s", title)

        except Exception as e:
            logger.warning("  [fail] Source '%s': %s", title, e)
            result.failed += 1
            result.failures.append({"title": title, "type": "source", "error": str(e)})

    return result


# ------------------------------------------------------------------
# Artifacts → Literature/Resource notes
# ------------------------------------------------------------------


async def _import_artifacts(
    client: Any,
    nb_id: str,
    nb_title: str,
    vault_path: Path,
    sync_state: SyncState,
    include_media: bool,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    result = ImportResult()
    nb_dir = sanitize_filename(nb_title)

    # Fetch raw artifact data for content extraction
    try:
        raw_artifacts = await client.artifacts._list_raw(nb_id)
    except Exception as e:
        logger.error("Failed to list raw artifacts: %s", e)
        result.failed += 1
        result.failures.append({"title": "Artifact listing", "type": "artifact", "error": str(e)})
        return result

    await asyncio.sleep(1)

    # Also get parsed artifact list for metadata
    try:
        artifacts = await client.artifacts.list(nb_id)
    except Exception:
        artifacts = []

    await asyncio.sleep(1)

    # Build a map of artifact_id → parsed Artifact for metadata
    art_map = {a.id: a for a in artifacts}

    # Process raw artifacts for reports, quizzes, flashcards
    for raw in raw_artifacts:
        if not isinstance(raw, list) or len(raw) < 5:
            continue

        art_id = str(raw[0])
        art_title = str(raw[1]) if len(raw) > 1 else "Untitled"
        art_type = raw[2] if len(raw) > 2 else 0
        art_status = raw[4] if len(raw) > 4 else 0

        if art_status != _STATUS_COMPLETED:
            continue

        if not force and sync_state.is_synced(nb_id, "artifacts", art_id):
            result.skipped += 1
            if verbose:
                logger.info("  [skip] Artifact: %s (already synced)", art_title)
            continue

        try:
            if art_type == _TYPE_REPORT:
                await _import_report(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)

            elif art_type == _TYPE_QUIZ_FLASHCARD:
                # Determine variant: 1=flashcard, 2=quiz
                variant = None
                parsed_art = art_map.get(art_id)
                if parsed_art:
                    variant = parsed_art.variant
                if variant is None and len(raw) > 9 and isinstance(raw[9], list) and len(raw[9]) > 1:
                    opts = raw[9][1]
                    if isinstance(opts, list) and len(opts) > 0:
                        variant = opts[0]

                if variant == 2:
                    await _import_quiz(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)
                else:
                    await _import_flashcard(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)

            elif art_type == _TYPE_AUDIO:
                if include_media:
                    await _import_binary(client, "download_audio", "mp4", "audio", art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)
                elif verbose:
                    logger.info("  [skip] Audio: %s (--include-media not set)", art_title)

            elif art_type == _TYPE_VIDEO:
                if include_media:
                    await _import_binary(client, "download_video", "mp4", "video", art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)
                elif verbose:
                    logger.info("  [skip] Video: %s (--include-media not set)", art_title)

            elif art_type == _TYPE_INFOGRAPHIC:
                await _import_binary(client, "download_infographic", "png", "infographic", art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)

            elif art_type == _TYPE_SLIDE_DECK:
                await _import_binary(client, "download_slide_deck", "pdf", "slide_deck", art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result)

            elif art_type == _TYPE_DATA_TABLE:
                # Data tables — try to extract content like reports
                log_discovery("data_table", raw)
                text = find_content_string(raw)
                if text:
                    md = format_resource_note(
                        title=art_title, content=text,
                        notebook_title=nb_title, resource_type="data_table",
                    )
                    rel_path = f"3. Resources/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.md"
                    if dry_run:
                        logger.info("  [dry-run] %s", rel_path)
                    else:
                        write_note(vault_path, rel_path, md)
                        sync_state.mark_synced(nb_id, nb_title, "artifacts", art_id, art_title, rel_path)
                    result.imported += 1

        except Exception as e:
            logger.warning("  [fail] Artifact '%s': %s", art_title, e)
            result.failed += 1
            result.failures.append({"title": art_title, "type": "artifact", "error": str(e)})

    # Import mind maps from notes system
    r = await _import_mind_maps(client, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, force, verbose)
    result.merge(r)

    return result


async def _import_report(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result):
    text = extract_report_text(raw)
    if not text:
        text = "*[Report text could not be extracted. View in NotebookLM web UI.]*"

    md = format_literature_note(
        title=art_title, content=text,
        notebook_title=nb_title, author="NotebookLM Report",
    )
    rel_path = f"5. Zettelkasten/10. Literature/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.md"

    if dry_run:
        logger.info("  [dry-run] %s", rel_path)
    else:
        write_note(vault_path, rel_path, md)
        sync_state.mark_synced(nb_id, nb_title, "artifacts", art_id, art_title, rel_path)
    result.imported += 1
    if verbose:
        logger.info("  [import] Report: %s", art_title)


async def _import_quiz(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result):
    text = extract_quiz_content(raw)
    if not text:
        text = "*[Quiz content could not be extracted. View in NotebookLM web UI.]*"

    md = format_resource_note(
        title=art_title, content=text,
        notebook_title=nb_title, resource_type="quiz",
    )
    rel_path = f"3. Resources/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.md"

    if dry_run:
        logger.info("  [dry-run] %s", rel_path)
    else:
        write_note(vault_path, rel_path, md)
        sync_state.mark_synced(nb_id, nb_title, "artifacts", art_id, art_title, rel_path)
    result.imported += 1
    if verbose:
        logger.info("  [import] Quiz: %s", art_title)


async def _import_flashcard(raw, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result):
    text = extract_flashcard_content(raw)
    if not text:
        text = "*[Flashcard content could not be extracted. View in NotebookLM web UI.]*"

    md = format_resource_note(
        title=art_title, content=text,
        notebook_title=nb_title, resource_type="flashcard",
    )
    rel_path = f"3. Resources/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.md"

    if dry_run:
        logger.info("  [dry-run] %s", rel_path)
    else:
        write_note(vault_path, rel_path, md)
        sync_state.mark_synced(nb_id, nb_title, "artifacts", art_id, art_title, rel_path)
    result.imported += 1
    if verbose:
        logger.info("  [import] Flashcard: %s", art_title)


async def _import_binary(client, download_method, ext, resource_type, art_id, art_title, nb_id, nb_title, nb_dir, vault_path, sync_state, dry_run, verbose, result):
    """Download a binary artifact and create a Resource link note."""
    binary_rel = f"7. Attachments/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.{ext}"
    note_rel = f"3. Resources/NotebookLM/{nb_dir}/{sanitize_filename(art_title)}.md"

    if dry_run:
        logger.info("  [dry-run] %s", binary_rel)
        logger.info("  [dry-run] %s", note_rel)
        result.imported += 1
        return

    abs_binary = vault_path / binary_rel
    abs_binary.parent.mkdir(parents=True, exist_ok=True)

    download_fn = getattr(client.artifacts, download_method)
    await download_fn(nb_id, str(abs_binary), artifact_id=art_id)
    await asyncio.sleep(1)

    md = format_resource_note(
        title=art_title, content="",
        notebook_title=nb_title, resource_type=resource_type,
        attachment_path=binary_rel,
    )
    write_note(vault_path, note_rel, md)
    sync_state.mark_synced(nb_id, nb_title, "artifacts", art_id, art_title, note_rel)
    result.imported += 1
    if verbose:
        logger.info("  [import] %s: %s", resource_type.capitalize(), art_title)


# ------------------------------------------------------------------
# Mind maps
# ------------------------------------------------------------------


async def _import_mind_maps(
    client: Any,
    nb_id: str,
    nb_title: str,
    nb_dir: str,
    vault_path: Path,
    sync_state: SyncState,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    result = ImportResult()

    try:
        mind_maps = await client.notes.list_mind_maps(nb_id)
    except Exception as e:
        logger.warning("Failed to list mind maps: %s", e)
        return result

    await asyncio.sleep(1)

    for mm in mind_maps:
        if not isinstance(mm, list) or len(mm) < 2:
            continue

        mm_id = str(mm[0])

        if not force and sync_state.is_synced(nb_id, "artifacts", mm_id):
            result.skipped += 1
            continue

        try:
            # Extract content and title from raw mind map data
            content_str = None
            title = "Mind Map"

            if isinstance(mm[1], list):
                inner = mm[1]
                if len(inner) > 1 and isinstance(inner[1], str):
                    content_str = inner[1]
                if len(inner) > 4 and isinstance(inner[4], str):
                    title = inner[4]
            elif isinstance(mm[1], str):
                content_str = mm[1]

            if not content_str:
                continue

            # Save raw JSON to Attachments
            json_rel = f"7. Attachments/NotebookLM/{nb_dir}/{sanitize_filename(title)}.json"
            note_rel = f"3. Resources/NotebookLM/{nb_dir}/{sanitize_filename(title)}.md"

            if dry_run:
                logger.info("  [dry-run] %s", json_rel)
                logger.info("  [dry-run] %s", note_rel)
                result.imported += 1
                continue

            write_note(vault_path, json_rel, content_str)

            # Convert to markdown tree
            try:
                data = json.loads(content_str)
                markdown_tree = mindmap_to_markdown(data)
            except json.JSONDecodeError:
                markdown_tree = content_str

            md = format_resource_note(
                title=title, content=markdown_tree,
                notebook_title=nb_title, resource_type="mindmap",
                attachment_path=json_rel,
            )
            write_note(vault_path, note_rel, md)
            sync_state.mark_synced(nb_id, nb_title, "artifacts", mm_id, title, note_rel)
            result.imported += 1
            if verbose:
                logger.info("  [import] Mind Map: %s", title)

        except Exception as e:
            logger.warning("  [fail] Mind Map '%s': %s", mm_id, e)
            result.failed += 1
            result.failures.append({"title": mm_id, "type": "mind_map", "error": str(e)})

    return result


# ------------------------------------------------------------------
# User notes → Inbox
# ------------------------------------------------------------------


async def _import_notes(
    client: Any,
    nb_id: str,
    nb_title: str,
    vault_path: Path,
    sync_state: SyncState,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    result = ImportResult()
    nb_dir = sanitize_filename(nb_title)

    try:
        notes = await client.notes.list(nb_id)
    except Exception as e:
        logger.error("Failed to list notes: %s", e)
        result.failed += 1
        result.failures.append({"title": "Note listing", "type": "note", "error": str(e)})
        return result

    await asyncio.sleep(1)

    for note in notes:
        nid = note.id
        title = note.title or f"Note {nid[:8]}"
        content = note.content or ""

        if not force and sync_state.is_synced(nb_id, "notes", nid):
            result.skipped += 1
            if verbose:
                logger.info("  [skip] Note: %s (already synced)", title)
            continue

        try:
            md = format_inbox_note(
                title=title, content=content, notebook_title=nb_title,
            )
            rel_path = f"5. Zettelkasten/00. Inbox/NotebookLM/{nb_dir}/{sanitize_filename(title)}.md"

            if dry_run:
                logger.info("  [dry-run] %s", rel_path)
            else:
                write_note(vault_path, rel_path, md)
                sync_state.mark_synced(nb_id, nb_title, "notes", nid, title, rel_path)

            result.imported += 1
            if verbose:
                logger.info("  [import] Note: %s", title)

        except Exception as e:
            logger.warning("  [fail] Note '%s': %s", title, e)
            result.failed += 1
            result.failures.append({"title": title, "type": "note", "error": str(e)})

    return result


# ------------------------------------------------------------------
# Chat history → Single Inbox note
# ------------------------------------------------------------------


async def _import_chat_history(
    client: Any,
    nb_id: str,
    nb_title: str,
    vault_path: Path,
    sync_state: SyncState,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult:
    result = ImportResult()
    nb_dir = sanitize_filename(nb_title)

    if not force and sync_state.is_chat_synced(nb_id):
        result.skipped += 1
        if verbose:
            logger.info("  [skip] Chat history (already synced)")
        return result

    try:
        raw_history = await client.chat.get_history(nb_id, limit=100)
        await asyncio.sleep(1)
    except Exception as e:
        logger.warning("  [fail] Chat history: %s", e)
        result.failed += 1
        result.failures.append({"title": "Chat History", "type": "chat", "error": str(e)})
        return result

    if not raw_history:
        if verbose:
            logger.info("  [skip] Chat history (empty)")
        return result

    # Log discovery for chat structure
    logger.debug("DISCOVERY [chat_history]: %s", json.dumps(
        raw_history[:2] if isinstance(raw_history, list) else raw_history,
        ensure_ascii=False, default=str,
    )[:2000])

    # Parse chat history — structure discovered at runtime
    content = _parse_chat_history(raw_history)

    if not content.strip():
        if verbose:
            logger.info("  [skip] Chat history (no parseable content)")
        return result

    md = format_inbox_note(
        title="Chat History", content=content, notebook_title=nb_title,
    )
    rel_path = f"5. Zettelkasten/00. Inbox/NotebookLM/{nb_dir}/Chat History.md"

    if dry_run:
        logger.info("  [dry-run] %s", rel_path)
    else:
        write_note(vault_path, rel_path, md)
        sync_state.mark_chat_synced(nb_id, nb_title)

    result.imported += 1
    if verbose:
        logger.info("  [import] Chat History")

    return result


def _parse_chat_history(raw: Any) -> str:
    """Parse raw chat history data into markdown.

    Structure is unknown at design time — this uses defensive parsing
    to extract question/answer pairs from whatever structure the API returns.
    """
    lines = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, list):
                # Try to extract Q&A pairs from nested structure
                q, a = _extract_qa_pair(item)
                if q or a:
                    if q:
                        lines.append(f"### Q: {q}")
                    if a:
                        lines.append(f"\n{a}")
                    lines.append("\n---\n")
            elif isinstance(item, dict):
                q = item.get("query") or item.get("question") or ""
                a = item.get("answer") or item.get("response") or ""
                if q or a:
                    if q:
                        lines.append(f"### Q: {q}")
                    if a:
                        lines.append(f"\n{a}")
                    lines.append("\n---\n")

    if not lines:
        # Fallback: dump as JSON code block
        return f"```json\n{json.dumps(raw, ensure_ascii=False, indent=2, default=str)}\n```"

    return "\n".join(lines)


def _extract_qa_pair(item: list) -> tuple:
    """Try to extract a question/answer pair from a list item."""
    q = ""
    a = ""

    # Common patterns: [answer, null, type] or [text, metadata, type]
    for sub in item:
        if isinstance(sub, str) and len(sub) > 10:
            if not q:
                q = sub
            elif not a:
                a = sub
        elif isinstance(sub, list):
            for subsub in sub:
                if isinstance(subsub, str) and len(subsub) > 10:
                    if not a:
                        a = subsub

    return q, a


# ------------------------------------------------------------------
# File I/O
# ------------------------------------------------------------------


def write_note(vault_path: Path, relative_path: str, content: str) -> None:
    """Create parent directories if needed. Write content as UTF-8."""
    full_path = vault_path / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


def write_binary(vault_path: Path, relative_path: str, data: bytes) -> None:
    """Create parent directories if needed. Write binary data."""
    full_path = vault_path / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)
