"""Sync state tracking to prevent duplicate imports.

Persists to {vault_root}/.notebooklm-sync.json.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class SyncState:
    """Track which NotebookLM items have been imported to the vault."""

    FILENAME = ".notebooklm-sync.json"
    VERSION = 1

    def __init__(self, vault_path: Path) -> None:
        self._vault_path = vault_path
        self._file_path = vault_path / self.FILENAME
        self._data: Dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Read JSON file. If not found, initialize empty state."""
        if self._file_path.exists():
            with open(self._file_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {
                "version": self.VERSION,
                "last_sync": None,
                "notebooks": {},
            }

    def save(self) -> None:
        """Write current state to JSON file atomically. Update last_sync."""
        self._data["last_sync"] = datetime.now().isoformat(timespec="seconds")
        tmp_path = self._file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._file_path)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def is_synced(self, notebook_id: str, item_type: str, item_id: str) -> bool:
        """Return True if this item has been previously imported.

        Args:
            notebook_id: Notebook identifier.
            item_type: One of 'sources', 'artifacts', 'notes'.
            item_id: Item identifier.
        """
        nb = self._data["notebooks"].get(notebook_id, {})
        bucket = nb.get(item_type, {})
        return item_id in bucket

    def is_chat_synced(self, notebook_id: str) -> bool:
        """Return True if chat history has been imported for this notebook."""
        nb = self._data["notebooks"].get(notebook_id, {})
        return nb.get("chat_synced_at") is not None

    # ------------------------------------------------------------------
    # Mark synced
    # ------------------------------------------------------------------

    def mark_synced(
        self,
        notebook_id: str,
        notebook_title: str,
        item_type: str,
        item_id: str,
        title: str,
        file_path: str,
    ) -> None:
        """Record that an item has been imported."""
        nb = self._ensure_notebook(notebook_id, notebook_title)
        if item_type not in nb:
            nb[item_type] = {}
        nb[item_type][item_id] = {
            "title": title,
            "file_path": file_path,
            "synced_at": datetime.now().isoformat(timespec="seconds"),
        }

    def mark_chat_synced(self, notebook_id: str, notebook_title: str) -> None:
        """Record that chat history has been imported."""
        nb = self._ensure_notebook(notebook_id, notebook_title)
        nb["chat_synced_at"] = datetime.now().isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def get_notebook_summary(self, notebook_id: str) -> Dict[str, Any]:
        """Return counts for a single notebook."""
        nb = self._data["notebooks"].get(notebook_id, {})
        return {
            "title": nb.get("title", "Unknown"),
            "sources": len(nb.get("sources", {})),
            "artifacts": len(nb.get("artifacts", {})),
            "notes": len(nb.get("notes", {})),
            "chat_synced": nb.get("chat_synced_at") is not None,
            "last_sync": nb.get("chat_synced_at")
            or self._latest_synced_at(nb),
        }

    def get_all_summaries(self) -> List[Dict[str, Any]]:
        """Return summary for every tracked notebook."""
        summaries = []
        for nb_id in self._data["notebooks"]:
            summary = self.get_notebook_summary(nb_id)
            summary["notebook_id"] = nb_id
            summaries.append(summary)
        return summaries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_notebook(self, notebook_id: str, title: str) -> Dict[str, Any]:
        """Create notebook entry if not present, return it."""
        notebooks = self._data["notebooks"]
        if notebook_id not in notebooks:
            notebooks[notebook_id] = {
                "title": title,
                "sources": {},
                "artifacts": {},
                "notes": {},
                "chat_synced_at": None,
            }
        else:
            notebooks[notebook_id]["title"] = title
        return notebooks[notebook_id]

    def _latest_synced_at(self, nb: Dict[str, Any]) -> str:
        """Find the most recent synced_at across all item buckets."""
        latest = ""
        for bucket_key in ("sources", "artifacts", "notes"):
            for item in nb.get(bucket_key, {}).values():
                ts = item.get("synced_at", "")
                if ts > latest:
                    latest = ts
        return latest or None
