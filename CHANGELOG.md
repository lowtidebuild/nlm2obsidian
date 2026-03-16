# Changelog

All notable changes to nlm2obsidian will be documented in this file.

---

## [0.1.0] — 2026-03-17

### First Release

The initial release of nlm2obsidian — a CLI tool that imports Google NotebookLM content into an Obsidian vault organized with Zettelkasten/PARA conventions.

---

### What's Included

**4 CLI Commands**

| Command | Description |
|---------|-------------|
| `login` | Google authentication via browser (delegates to notebooklm-py) |
| `list` | Display all notebooks with source counts |
| `import` | Fetch and convert NotebookLM content into Obsidian markdown |
| `status` | Show sync history per notebook |

**11 Content Types Supported**

| Content | Note Type | Vault Location |
|---------|-----------|----------------|
| Sources | Literature | `5. Zettelkasten/10. Literature/NotebookLM/` |
| Reports (Briefing Doc, Study Guide, Blog Post) | Literature | same |
| Quizzes | Resource | `3. Resources/NotebookLM/` |
| Flashcards | Resource | same |
| Mind Maps | Resource + raw JSON | `3. Resources/` + `7. Attachments/` |
| Audio Overviews | Resource + binary | same |
| Video Overviews | Resource + binary | same |
| Infographics | Resource + binary | same |
| Slide Decks | Resource + binary | same |
| User Notes | Inbox | `5. Zettelkasten/00. Inbox/NotebookLM/` |
| Chat History | Inbox | same |

**Import Features**

- `--notebook` partial name matching (case-insensitive), or `"all"` for every notebook
- `--type` filter: `sources`, `artifacts`, `notes`, or `all`
- `--dry-run` to preview without writing files
- `--force` to re-import already-synced items
- `--include-media` to download audio/video binaries
- `-v` for per-item progress logging

**Sync & Safety**

- Duplicate prevention via `.notebooklm-sync.json` at vault root
- Per-item error handling — one failure doesn't stop the rest
- 1-second rate limiting between API calls
- Atomic sync state writes (temp file + rename)
- Never deletes files from the vault

---

### Vault Convention Compliance

Frontmatter follows the vault's Zettelkasten/PARA rules:

- **Literature notes** (ZK): `type`, `status`, `created`, `updated`, `source`, `author`
- **Resource notes** (PARA): `type`, `status` only — no `created`/`updated` (OS metadata)
- **Inbox notes** (ZK): `type`, `status`, `created`, `updated`, `source`
- **Tags**: PascalCase, max 3 per note (`#NotebookLM #NotebookTitle #ContentType`)

---

### Known Limitations

- **Source content is AI summary only.** The NotebookLM API (`get_guide()`) returns an AI-generated summary and keywords, not the full source text. The `author` field is set to `"NotebookLM AI Summary"` to indicate this.
- **Report/Quiz/Flashcard text extraction is best-effort.** These are parsed from undocumented raw API arrays via `raw_parser.py`. If extraction fails, a placeholder note is created.
- **Chat history structure is discovered at runtime.** The raw API response is parsed defensively; if structured parsing fails, the data is preserved as a JSON code block.
- **Import only.** No bidirectional sync, no scheduled runs, no Obsidian plugin.

---

### Technical Details

- **Python**: 3.9+
- **Dependencies**: `click` (CLI), `notebooklm-py` 0.1.1 (API client)
- **Architecture**: 5 modules — `cli.py`, `importer.py`, `formatters.py`, `raw_parser.py`, `sync_state.py`
- **Auth**: Browser-based Google login via notebooklm-py (cookies stored in `~/.notebooklm/`)

---

[0.1.0]: https://github.com/lowtidebuild/nlm2obsidian/releases/tag/v0.1.0
