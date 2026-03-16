"""Parse raw artifact data from notebooklm-py _list_raw().

The notebooklm-py library stores artifact content in undocumented array
indices. This module uses defensive parsing with fallback heuristics to
extract report text, quiz questions, and flashcard content.

On first encounter of each artifact type, the full structure is logged
at DEBUG level for developer inspection.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Set

logger = logging.getLogger(__name__)

# Track which artifact types we've already logged
_discovered_types: Set[str] = set()


# ------------------------------------------------------------------
# Public extraction functions
# ------------------------------------------------------------------


def extract_report_text(raw_artifact: list) -> str:
    """Extract report markdown text from a raw type-2 artifact array.

    Known artifact array structure:
      [0]=id, [1]=title, [2]=type, [4]=status,
      [6]=audio_meta, [8]=video_meta, [9]=options, [16]=slide_meta

    Report text is searched at likely indices, then falls back to
    recursive content string search.
    """
    log_discovery("report", raw_artifact)

    # Try known likely positions for report text content
    # Reports are type 2 — their content is typically in the metadata area
    for idx in (7, 6, 8, 5, 3, 10, 11, 12, 13, 14):
        text = _try_extract_text_at(raw_artifact, idx)
        if text and _looks_like_content(text):
            return text

    # Fallback: recursive search for longest markdown-like string
    return find_content_string(raw_artifact)


def extract_quiz_content(raw_artifact: list) -> str:
    """Extract quiz questions from a raw type-4 variant-2 artifact array.

    Returns formatted markdown with numbered questions and answers.
    """
    log_discovery("quiz", raw_artifact)

    # Try to find structured quiz data (could be JSON or plain text)
    raw_content = _find_structured_content(raw_artifact)

    if raw_content:
        # Try to parse as JSON first
        parsed = _try_parse_json(raw_content)
        if parsed:
            return _format_quiz_from_json(parsed)
        # If it looks like text content, return it as-is
        if _looks_like_content(raw_content):
            return raw_content

    # Fallback
    text = find_content_string(raw_artifact)
    if text:
        parsed = _try_parse_json(text)
        if parsed:
            return _format_quiz_from_json(parsed)
        return text

    return ""


def extract_flashcard_content(raw_artifact: list) -> str:
    """Extract flashcard pairs from a raw type-4 variant-1 artifact array.

    Returns formatted markdown with Front/Back pairs.
    """
    log_discovery("flashcard", raw_artifact)

    raw_content = _find_structured_content(raw_artifact)

    if raw_content:
        parsed = _try_parse_json(raw_content)
        if parsed:
            return _format_flashcards_from_json(parsed)
        if _looks_like_content(raw_content):
            return raw_content

    text = find_content_string(raw_artifact)
    if text:
        parsed = _try_parse_json(text)
        if parsed:
            return _format_flashcards_from_json(parsed)
        return text

    return ""


def find_content_string(raw_artifact: list, min_length: int = 50) -> str:
    """Walk the raw artifact array recursively, find the longest
    string that looks like markdown content.
    """
    candidates: List[str] = []
    _collect_strings(raw_artifact, candidates, min_length)

    if not candidates:
        return ""

    # Sort by length descending, prefer markdown-like strings
    candidates.sort(key=lambda s: (1 if _looks_like_content(s) else 0, len(s)), reverse=True)
    return candidates[0]


# ------------------------------------------------------------------
# Discovery logging
# ------------------------------------------------------------------


def log_discovery(artifact_type: str, raw_data: list) -> None:
    """Log the raw array structure once per type for debugging."""
    if artifact_type in _discovered_types:
        return
    _discovered_types.add(artifact_type)

    # Create a truncated representation for logging
    truncated = _truncate_for_log(raw_data, max_str_len=100)
    logger.debug(
        "DISCOVERY [%s]: Raw artifact structure (first encounter):\n%s",
        artifact_type,
        json.dumps(truncated, ensure_ascii=False, indent=2, default=str),
    )


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _try_extract_text_at(raw: list, idx: int) -> Optional[str]:
    """Try to extract a text string at the given index, handling nesting."""
    if idx >= len(raw):
        return None

    val = raw[idx]

    if isinstance(val, str) and len(val) > 30:
        return val

    if isinstance(val, list):
        # Try common nesting patterns: [text], [[text]], [metadata, text]
        for item in val:
            if isinstance(item, str) and len(item) > 30:
                return item
            if isinstance(item, list):
                for sub in item:
                    if isinstance(sub, str) and len(sub) > 30:
                        return sub

    return None


def _find_structured_content(raw: list) -> Optional[str]:
    """Search for structured content (JSON or long text) in the artifact array."""
    # Check indices beyond the standard metadata positions
    for idx in range(len(raw)):
        if idx in (0, 1, 2, 4, 15):  # Skip known non-content indices
            continue

        val = raw[idx]
        text = _deep_find_text(val, min_len=80)
        if text:
            return text

    return None


def _deep_find_text(val: Any, min_len: int = 80, depth: int = 0) -> Optional[str]:
    """Recursively find a long text string in nested structures."""
    if depth > 10:
        return None

    if isinstance(val, str) and len(val) >= min_len:
        return val

    if isinstance(val, list):
        # First check direct children
        for item in val:
            if isinstance(item, str) and len(item) >= min_len:
                return item
        # Then recurse
        for item in val:
            if isinstance(item, list):
                result = _deep_find_text(item, min_len, depth + 1)
                if result:
                    return result

    return None


def _looks_like_content(text: str) -> bool:
    """Check if a string looks like markdown/text content (not a URL or ID)."""
    if not text or len(text) < 30:
        return False
    if text.startswith("http"):
        return False
    # Content typically has newlines, headers, or bullet points
    signals = ("\n", "#", "- ", "* ", "**", "1.", "2.", "3.")
    return any(s in text for s in signals)


def _collect_strings(data: Any, results: List[str], min_length: int, depth: int = 0) -> None:
    """Recursively collect long strings from nested data."""
    if depth > 15:
        return

    if isinstance(data, str):
        if len(data) >= min_length:
            results.append(data)
    elif isinstance(data, list):
        for item in data:
            _collect_strings(item, results, min_length, depth + 1)
    elif isinstance(data, dict):
        for val in data.values():
            _collect_strings(val, results, min_length, depth + 1)


def _try_parse_json(text: str) -> Any:
    """Try to parse a string as JSON. Return parsed data or None."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _format_quiz_from_json(data: Any) -> str:
    """Format parsed quiz JSON into markdown."""
    lines = []

    if isinstance(data, list):
        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                q = item.get("question") or item.get("q") or item.get("text") or ""
                a = item.get("answer") or item.get("a") or item.get("correct_answer") or ""
                options = item.get("options") or item.get("choices") or []
                lines.append(f"### Q{i}: {q}")
                if options:
                    for opt in options:
                        if isinstance(opt, str):
                            lines.append(f"- {opt}")
                        elif isinstance(opt, dict):
                            label = opt.get("text") or opt.get("label") or str(opt)
                            lines.append(f"- {label}")
                if a:
                    lines.append(f"\n**Answer:** {a}")
                lines.append("")
            elif isinstance(item, list) and len(item) >= 2:
                lines.append(f"### Q{i}: {item[0]}")
                lines.append(f"\n**Answer:** {item[1]}")
                lines.append("")

    if not lines:
        return json.dumps(data, ensure_ascii=False, indent=2)

    return "\n".join(lines)


def _format_flashcards_from_json(data: Any) -> str:
    """Format parsed flashcard JSON into markdown."""
    lines = []

    if isinstance(data, list):
        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                front = item.get("front") or item.get("question") or item.get("term") or item.get("q") or ""
                back = item.get("back") or item.get("answer") or item.get("definition") or item.get("a") or ""
                lines.append(f"### Card {i}")
                lines.append(f"**Front:** {front}")
                lines.append(f"**Back:** {back}")
                lines.append("")
            elif isinstance(item, list) and len(item) >= 2:
                lines.append(f"### Card {i}")
                lines.append(f"**Front:** {item[0]}")
                lines.append(f"**Back:** {item[1]}")
                lines.append("")

    if not lines:
        return json.dumps(data, ensure_ascii=False, indent=2)

    return "\n".join(lines)


def _truncate_for_log(data: Any, max_str_len: int = 100) -> Any:
    """Create a truncated copy of data for logging."""
    if isinstance(data, str):
        if len(data) > max_str_len:
            return data[:max_str_len] + f"... ({len(data)} chars)"
        return data
    elif isinstance(data, list):
        return [_truncate_for_log(item, max_str_len) for item in data]
    elif isinstance(data, dict):
        return {k: _truncate_for_log(v, max_str_len) for k, v in data.items()}
    return data
