"""Convert NotebookLM API content to Obsidian-compatible markdown.

All functions are pure — no I/O, no side effects.
Frontmatter follows vault conventions:
  - ZK Literature: type, status, created, updated, source, author
  - PARA Resource: type, status only (created/updated forbidden)
  - ZK Inbox: type, status, created, updated, source
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, List, Optional, Union


# ------------------------------------------------------------------
# Note formatters
# ------------------------------------------------------------------


def format_literature_note(
    title: str,
    content: str,
    notebook_title: str,
    source_type: str = "NotebookLM",
    author: str = "NotebookLM",
    created: str = "",
) -> str:
    """Return complete markdown string with Literature frontmatter.

    Goes to: 5. Zettelkasten/10. Literature/NotebookLM/{notebook}/
    """
    today = created or date.today().isoformat()
    nb_tag = notebook_title_to_tag(notebook_title)
    type_tag = _source_type_tag(source_type)

    tags = _build_tag_line("NotebookLM", nb_tag, type_tag)

    return (
        f"---\n"
        f"type: literature\n"
        f"status: active\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f'source: "NotebookLM - {notebook_title}"\n'
        f'author: "{author}"\n'
        f"---\n\n"
        f"{tags}\n"
        f"# {title}\n\n"
        f"{content}\n"
    )


def format_resource_note(
    title: str,
    content: str,
    notebook_title: str,
    resource_type: str = "",
    attachment_path: str = "",
) -> str:
    """Return complete markdown string with Resource frontmatter.

    Goes to: 3. Resources/NotebookLM/{notebook}/
    PARA folder — no created/updated fields (OS metadata used).
    """
    nb_tag = notebook_title_to_tag(notebook_title)
    type_tag = resource_type if resource_type else None

    tags = _build_tag_line("NotebookLM", nb_tag, type_tag)

    parts = [
        "---\n"
        "type: resource\n"
        "status: active\n"
        "---\n\n"
        f"{tags}\n"
        f"# {title}\n\n"
        f"{content}\n"
    ]

    if attachment_path:
        filename = attachment_path.rsplit("/", 1)[-1] if "/" in attachment_path else attachment_path
        parts.append(f"\n![[{filename}]]\n")

    return "".join(parts)


def format_inbox_note(
    title: str,
    content: str,
    notebook_title: str,
) -> str:
    """Return complete markdown string with Inbox frontmatter.

    Goes to: 5. Zettelkasten/00. Inbox/NotebookLM/{notebook}/
    ZK folder — created/updated allowed.
    """
    today = date.today().isoformat()
    nb_tag = notebook_title_to_tag(notebook_title)

    tags = _build_tag_line("NotebookLM", nb_tag)

    return (
        f"---\n"
        f"type: inbox\n"
        f"status: active\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f'source: "NotebookLM - {notebook_title}"\n'
        f"---\n\n"
        f"{tags}\n"
        f"# {title}\n\n"
        f"{content}\n"
    )


# ------------------------------------------------------------------
# Mind map conversion
# ------------------------------------------------------------------


def mindmap_to_markdown(data: Union[dict, list]) -> str:
    """Convert mind map JSON to indented markdown tree.

    Handles both 'children' and 'nodes' as possible child keys.
    Each node becomes '- {label}' with 2-space indent per depth level.
    """
    lines: List[str] = []
    _walk_node(data, 0, lines)
    return "\n".join(lines)


def _walk_node(node: Any, depth: int, lines: List[str]) -> None:
    """Recursively walk a mind map node."""
    indent = "  " * depth

    if isinstance(node, dict):
        # Extract label from common key names
        label = (
            node.get("name")
            or node.get("label")
            or node.get("text")
            or node.get("title")
            or ""
        )
        if label:
            lines.append(f"{indent}- {label}")

        # Recurse into children
        children = node.get("children") or node.get("nodes") or []
        for child in children:
            _walk_node(child, depth + (1 if label else 0), lines)

    elif isinstance(node, list):
        for item in node:
            _walk_node(item, depth, lines)

    elif isinstance(node, str) and node.strip():
        lines.append(f"{indent}- {node}")


# ------------------------------------------------------------------
# Filename sanitization
# ------------------------------------------------------------------

_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Strip illegal characters, trim whitespace, truncate."""
    clean = _ILLEGAL_CHARS.sub("", name)
    clean = clean.strip()
    if len(clean) > max_length:
        clean = clean[:max_length]
    return clean or "Untitled"


# ------------------------------------------------------------------
# Tag helpers
# ------------------------------------------------------------------

_TAG_STRIP = re.compile(r'[/\\:*?"<>|#\[\]{}()@!$%^&+=~`]')


def notebook_title_to_tag(title: str) -> str:
    """Convert notebook title to PascalCase tag without spaces.

    'AI 논문 스터디' → 'AI논문스터디'
    """
    # Strip special chars, remove spaces
    clean = _TAG_STRIP.sub("", title)
    clean = clean.replace(" ", "")
    return clean or "NotebookLM"


def _source_type_tag(source_type: str) -> Optional[str]:
    """Map source_type to a short tag name."""
    mapping = {
        "text": "article",
        "url": "article",
        "youtube": "video",
        "pdf": "article",
        "upload": "article",
        "text_file": "article",
        "spreadsheet": "article",
        "NotebookLM": None,
        "report": "report",
        "quiz": "quiz",
        "flashcard": "flashcard",
        "mindmap": "mindmap",
        "audio": "audio",
        "video": "video",
        "infographic": "infographic",
        "slide_deck": "slides",
    }
    return mapping.get(source_type)


def _build_tag_line(*tags: Optional[str]) -> str:
    """Build a tags line like '#NotebookLM #Tag2 #Tag3', max 3 tags."""
    valid = [t for t in tags if t]
    # Deduplicate preserving order
    seen = set()
    unique = []
    for t in valid:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    # Max 3 tags per vault convention
    unique = unique[:3]
    return " ".join(f"#{t}" for t in unique)
