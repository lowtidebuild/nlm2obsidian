# nlm2obsidian — Design Specification

## 1. Overview

**nlm2obsidian** is a Python CLI tool that imports content from Google NotebookLM — sources, artifacts, notes, and chat history — into an Obsidian vault organized with Zettelkasten/PARA conventions. It uses the notebooklm-py 0.3.4 library to access the NotebookLM API and converts each content type into the appropriate Obsidian note format (Literature, Resource, or Inbox). The tool tracks sync state to prevent duplicate imports and is designed for single-user, local execution.

---

## 2. Goals & Non-Goals

### Goals

- Import all NotebookLM content types (sources, reports, quizzes, flashcards, mind maps, audio, video, infographics, slide decks, user notes, chat history) into an Obsidian vault with correct note types and folder placement.
- Generate Obsidian-native markdown with proper frontmatter, tags, and internal links.
- Prevent duplicate imports via persistent sync state tracking.
- Support selective import by notebook name (partial match, case-insensitive) and content type.
- Provide dry-run mode for previewing imports without writing files.
- Handle individual item failures gracefully (skip and continue), reporting all failures at the end.

### Non-Goals

- **No bidirectional sync.** This tool imports from NotebookLM → Obsidian only. Changes made in Obsidian are never pushed back.
- **No scheduled/background sync.** The tool runs on-demand via CLI. No daemon, no cron, no watch mode.
- **No Obsidian plugin.** This is a standalone CLI tool, not an Obsidian community plugin.
- **No automated tests.** Validation is manual via CLI execution and Obsidian inspection.
- **No multi-user support.** Single vault, single NotebookLM account.

---

## 3. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                        CLI (cli.py)                      │
│  login | list | import | status                          │
│  Parses args, delegates to importer, wraps asyncio.run() │
└──────────┬──────────────────────────────────┬────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐          ┌─────────────────────────┐
│   Importer           │          │   SyncState              │
│   (importer.py)      │◄────────►│   (sync_state.py)        │
│                      │          │                          │
│  Orchestrates per-   │  check/  │  .notebooklm-sync.json   │
│  notebook import.    │  mark    │  at vault root            │
│  Routes content by   │          └─────────────────────────┘
│  type. Handles       │
│  errors per item.    │
└──────────┬───────────┘
           │
           ▼
┌─────────────────────┐          ┌─────────────────────────┐
│   notebooklm-py      │          │   Formatters             │
│   0.3.4 (external)   │          │   (formatters.py)        │
│                      │          │                          │
│  sources.list()      │          │  format_literature_note() │
│  sources.get_fulltext│  ───►    │  format_resource_note()   │
│  artifacts.*         │  content │  format_inbox_note()      │
│  notes.*             │          │  mindmap_to_markdown()    │
│  chat API            │          │  sanitize_filename()      │
└──────────────────────┘          └─────────────────────────┘
```

### Components

**CLI (`cli.py`)**

- **Responsibility:** Parse CLI arguments, dispatch to appropriate handler, wrap async calls with `asyncio.run()`.
- **Inputs:** Command-line arguments (subcommand, flags, options).
- **Outputs:** Console output (lists, progress, error summaries).
- **Dependencies:** Importer, SyncState, notebooklm-py client (for `login`, `list`).

**Importer (`importer.py`)**

- **Responsibility:** Orchestrate the import of a single notebook — iterate over content types, fetch content via API, pass to formatters, write files, update sync state. Handle per-item errors (skip and continue).
- **Inputs:** notebooklm-py client, notebook object, vault path, content type filter, flags (include-media, dry-run, force).
- **Outputs:** Markdown files and binary assets written to vault. Failure list returned to CLI.
- **Dependencies:** notebooklm-py client, Formatters, SyncState.

**Formatters (`formatters.py`)**

- **Responsibility:** Convert raw API content into Obsidian-compatible markdown strings with correct frontmatter, tags, and structure. Sanitize filenames. Convert mind map JSON to hierarchical markdown tree.
- **Inputs:** Raw content (text, metadata) from API responses.
- **Outputs:** Complete markdown strings ready to write to disk.
- **Dependencies:** None (pure functions, no I/O).

**SyncState (`sync_state.py`)**

- **Responsibility:** Track which items have been imported to prevent duplicates. Persist state to `.notebooklm-sync.json` at vault root.
- **Inputs:** Notebook ID, item type, item ID for lookups. Title and file path for marking synced.
- **Outputs:** Boolean (is_synced), side effect (JSON file write on save).
- **Dependencies:** None (filesystem I/O only).

---

## 4. Data Model

### Entities

**Notebook** (from notebooklm-py)

- `id`: string — unique notebook identifier
- `title`: string — display name
- Source of truth: NotebookLM API

**Source** (from notebooklm-py)

- `id`: string — unique source identifier
- `title`: string — source name
- `type`: string — source type (PDF, URL, text, etc.)
- Relationship: belongs to one Notebook
- Source of truth: NotebookLM API

**Artifact** (from notebooklm-py)

- `id`: string — unique artifact identifier
- `type`: string — report, quiz, flashcard, audio, video, infographic, slide_deck
- `title`: string (may be auto-generated)
- Relationship: belongs to one Notebook
- Source of truth: NotebookLM API

**Note** (from notebooklm-py)

- `id`: string — unique note identifier
- `content`: string — user-written note text
- Relationship: belongs to one Notebook
- Source of truth: NotebookLM API

**MindMap** (from notebooklm-py)

- `id`: string — unique mind map identifier
- `data`: JSON — hierarchical node structure (discovered at runtime)
- Relationship: belongs to one Notebook
- Source of truth: NotebookLM API

**ChatHistory** (from notebooklm-py)

- Structure: list of messages (discovered at runtime via chat API)
- Relationship: belongs to one Notebook
- Source of truth: NotebookLM API

**SyncRecord** (local, managed by SyncState)

- `notebook_id`: string
- `item_type`: string — one of: source, artifact, note, chat
- `item_id`: string
- `title`: string — display name at time of sync
- `file_path`: string — relative path within vault
- `synced_at`: ISO 8601 datetime
- Source of truth: `.notebooklm-sync.json`

### Sync State File Structure

Location: `{vault_root}/.notebooklm-sync.json`

```json
{
  "version": 1,
  "last_sync": "2026-03-16T10:30:00",
  "notebooks": {
    "<notebook_id>": {
      "title": "AI 논문 스터디",
      "sources": {
        "<source_id>": {
          "title": "Attention Is All You Need",
          "file_path": "5. Zettelkasten/10. Literature/NotebookLM/AI 논문 스터디/Attention Is All You Need.md",
          "synced_at": "2026-03-16T10:30:00"
        }
      },
      "artifacts": { "<artifact_id>": { "title": "...", "file_path": "...", "synced_at": "..." } },
      "notes": { "<note_id>": { "title": "...", "file_path": "...", "synced_at": "..." } },
      "chat_synced_at": "2026-03-16T10:30:00"
    }
  }
}
```

### Content Type → Vault Path Mapping

| Content Type | Vault Path | Note Type |
|---|---|---|
| Source (fulltext) | `5. Zettelkasten/10. Literature/NotebookLM/{notebook}/` | Literature |
| Report | `5. Zettelkasten/10. Literature/NotebookLM/{notebook}/` | Literature |
| Quiz | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Flashcard | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Mind map (.json) | `7. Attachments/NotebookLM/{notebook}/` | — (raw file) |
| Mind map (note) | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Audio (binary) | `7. Attachments/NotebookLM/{notebook}/` | — (raw file) |
| Audio (link note) | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Video (binary) | `7. Attachments/NotebookLM/{notebook}/` | — (raw file) |
| Video (link note) | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Infographic (binary) | `7. Attachments/NotebookLM/{notebook}/` | — (raw file) |
| Infographic (link note) | `3. Resources/NotebookLM/{notebook}/` | Resource |
| Slide deck (binary) | `7. Attachments/NotebookLM/{notebook}/` | — (raw file) |
| Slide deck (link note) | `3. Resources/NotebookLM/{notebook}/` | Resource |
| User note | `5. Zettelkasten/00. Inbox/NotebookLM/{notebook}/` | Inbox |
| Chat history | `5. Zettelkasten/00. Inbox/NotebookLM/{notebook}/Chat History.md` | Inbox |

### Filename Sanitization Rules

- Strip characters: `/ \ : * ? " < > |`
- Replace stripped characters with empty string
- Truncate to 200 characters (before extension)
- Trim leading/trailing whitespace

---

## 5. User Flows

### Flow 1: Login

- **Trigger:** `nlm2obsidian login`
- **Steps:**
  1. CLI wraps `notebooklm login` command.
  2. Browser opens for Google authentication.
  3. Token is stored by notebooklm-py internally.
- **Success:** "Login successful" message printed.
- **Error:** Authentication failure → print error message from notebooklm-py, exit code 1.

### Flow 2: List Notebooks

- **Trigger:** `nlm2obsidian list`
- **Steps:**
  1. CLI creates notebooklm-py client.
  2. Fetch all notebooks via `client.notebooks.list()`.
  3. For each notebook, fetch source count and artifact count.
  4. Print table: notebook title, ID, source count, artifact count.
- **Success:** Table printed to stdout.
- **Error:** Auth expired → "Session expired. Run `nlm2obsidian login` first.", exit code 1. Network error → print error, exit code 1.

### Flow 3: Import (Main Flow)

- **Trigger:** `nlm2obsidian import [OPTIONS]`
- **Steps:**
  1. Parse options: `--vault`, `--notebook`, `--type`, `--include-media`, `--dry-run`, `--force`, `--verbose`.
  2. Load SyncState from `{vault}/.notebooklm-sync.json`.
  3. Fetch all notebooks via API.
  4. Filter notebooks by `--notebook` value (partial match, case-insensitive). If `"all"`, keep all. If no match found → error: "No notebook matching '{value}'. Run `nlm2obsidian list` to see available notebooks.", exit code 1. If multiple match → process all matched notebooks.
  5. For each matched notebook, call `import_notebook()`:
     - **5a. Sources** (if `--type` includes sources):
       - List sources via API.
       - For each source: check sync state (skip if synced and not `--force`) → fetch fulltext (fallback to guide) → format as Literature note → write to vault (or print path if `--dry-run`) → mark synced.
     - **5b. Artifacts** (if `--type` includes artifacts):
       - List artifacts via API.
       - For each artifact: check sync state → route by type:
         - Report → fetch via `download_report()` → format as Literature note → write.
         - Quiz/Flashcard → fetch via `_list_raw()` → parse structure → format as Resource note → write.
         - Mind map → fetch via `notes.list_mind_maps()` → save raw .json to Attachments → convert to markdown tree → format as Resource note → write.
         - Audio/Video → if `--include-media`: download binary to Attachments → create Resource link note. If not `--include-media`: skip with verbose log.
         - Infographic/Slide deck → download binary to Attachments → create Resource link note.
       - Mark synced after each item.
     - **5c. Notes** (if `--type` includes notes):
       - List user notes via API.
       - For each note: check sync state → format as Inbox note → write.
     - **5d. Chat history** (if `--type` includes notes):
       - Fetch chat history via chat API.
       - Check sync state (uses `chat_synced_at` per notebook).
       - Format as single Inbox note (`Chat History.md`) → write (overwrite if `--force`).
     - Save sync state after each notebook completes.
  6. Print summary: X items imported, Y skipped (already synced), Z failed.
  7. If any failures: print failure list (item title, type, error message).
- **Success:** Exit code 0, summary printed.
- **Error per item:** Skip failed item, add to failure list, continue processing. 1-second delay between API requests (rate limit).
- **Fatal errors:** Auth expired → message + exit code 1. Vault path not found → message + exit code 1.

### Flow 4: Status

- **Trigger:** `nlm2obsidian status`
- **Steps:**
  1. Load SyncState from vault.
  2. For each notebook in state: print notebook title, count of synced sources/artifacts/notes, last sync time.
  3. Print total counts.
- **Success:** Status table printed.
- **Error:** No sync file found → "No sync history found. Run `nlm2obsidian import` first."

### Flow 5: Dry Run (variant of Flow 3)

- **Trigger:** `nlm2obsidian import --dry-run [OPTIONS]`
- **Steps:** Same as Flow 3 but Step 5 skips all file writes and sync state updates. Instead, prints each file that *would* be created with its full vault path.
- **Success:** List of planned file paths printed. No files created, no state changed.

---

## 6. API Contracts / Interfaces

### 6.1 CLI Interface (`cli.py`)

```
nlm2obsidian login
nlm2obsidian list
nlm2obsidian import [OPTIONS]
nlm2obsidian status
```

**`import` options:**

| Option | Type | Default | Description |
|---|---|---|---|
| `--vault` | PATH | `/Users/kpsfamily/Obsidian` | Obsidian vault root |
| `--notebook` | STRING | required | Notebook name (partial match) or `"all"` |
| `--type` | CHOICE | `all` | `all`, `sources`, `artifacts`, `notes` |
| `--include-media` | FLAG | `False` | Download audio/video binaries |
| `--dry-run` | FLAG | `False` | Preview only, no writes |
| `--force` | FLAG | `False` | Re-import already synced items |
| `--verbose` / `-v` | FLAG | `False` | Verbose logging |

**Exit codes:**

- `0` — success (even if some items were skipped)
- `1` — fatal error (auth, network, invalid vault path, no notebook match)

### 6.2 SyncState (`sync_state.py`)

```python
class SyncState:
    def __init__(self, vault_path: Path) -> None
        """Load or initialize sync state from {vault_path}/.notebooklm-sync.json"""

    def load(self) -> None
        """Read JSON file. If not found, initialize empty state."""

    def save(self) -> None
        """Write current state to JSON file. Update last_sync timestamp."""

    def is_synced(self, notebook_id: str, item_type: str, item_id: str) -> bool
        """Return True if this item has been previously imported.
        item_type: 'source' | 'artifact' | 'note'
        For chat history, use is_chat_synced() instead."""

    def is_chat_synced(self, notebook_id: str) -> bool
        """Return True if chat history has been imported for this notebook."""

    def mark_synced(self, notebook_id: str, item_type: str, item_id: str,
                    title: str, file_path: str) -> None
        """Record that an item has been imported. Sets synced_at to now."""

    def mark_chat_synced(self, notebook_id: str) -> None
        """Record that chat history has been imported. Sets chat_synced_at to now."""

    def get_notebook_summary(self, notebook_id: str) -> dict
        """Return counts: {'sources': int, 'artifacts': int, 'notes': int, 'last_sync': str}"""

    def get_all_summaries(self) -> list[dict]
        """Return summary for every tracked notebook."""
```

### 6.3 Formatters (`formatters.py`)

```python
def format_literature_note(
    title: str,
    content: str,
    notebook_title: str,
    source_type: str = "NotebookLM",
    author: str = "NotebookLM",
    created: str = "",       # ISO date, defaults to today
) -> str
    """Return complete markdown string with Literature frontmatter.
    Includes: YAML frontmatter, tags line, content body."""

def format_resource_note(
    title: str,
    content: str,
    notebook_title: str,
    resource_type: str = "",  # "quiz", "flashcard", "mindmap", "audio", "video", etc.
    attachment_path: str = "", # relative vault path to linked binary, if any
) -> str
    """Return complete markdown string with Resource frontmatter.
    If attachment_path is provided, includes an Obsidian embed/link."""

def format_inbox_note(
    title: str,
    content: str,
    notebook_title: str,
) -> str
    """Return complete markdown string with Inbox frontmatter."""

def mindmap_to_markdown(data: dict | list) -> str
    """Convert mind map JSON (hierarchical nodes) to indented markdown tree.
    Uses '- ' prefix with 2-space indent per level.
    Structure discovered at runtime; handles nested 'children' or 'nodes' keys."""

def sanitize_filename(name: str, max_length: int = 200) -> str
    """Strip illegal characters (/ \\ : * ? \" < > |), trim whitespace,
    truncate to max_length. Return safe filename string."""
```

**Literature Note output format:**

```markdown
---
type: literature
status: active
created: 2026-03-16
updated: 2026-03-16
source: "NotebookLM - {notebook_title}"
author: "{author}"
---

Tags: #NotebookLM #{notebook_title_tag} #{source_type_tag}

# {title}

{content}
```

**Resource Note output format:**

```markdown
---
type: resource
status: active
created: 2026-03-16
updated: 2026-03-16
source: "NotebookLM - {notebook_title}"
resource_type: "{resource_type}"
---

Tags: #NotebookLM #{notebook_title_tag} #{resource_type_tag}

# {title}

{content}

<!-- attachment link if applicable -->
![[{attachment_filename}]]
```

**Inbox Note output format:**

```markdown
---
type: inbox
status: active
created: 2026-03-16
updated: 2026-03-16
source: "NotebookLM - {notebook_title}"
---

Tags: #NotebookLM #{notebook_title_tag}

# {title}

{content}
```

**Tag generation rule:** Notebook title is converted to a tag by replacing spaces with underscores and stripping special characters. Example: `"AI 논문 스터디"` → `#AI_논문_스터디`.

### 6.4 Importer (`importer.py`)

```python
async def import_notebook(
    client,                    # notebooklm-py client instance
    notebook,                  # Notebook object from API
    vault_path: Path,
    content_types: list[str],  # subset of ["sources", "artifacts", "notes"]
    sync_state: SyncState,
    include_media: bool,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> ImportResult
    """Import all requested content types from one notebook.
    Returns ImportResult with counts and failure list."""

async def try_get_fulltext_or_guide(client, notebook_id: str, source) -> str
    """Attempt get_fulltext() first (0.3.x).
    Fallback to get_guide() → extract summary.
    Returns content string."""

async def import_artifact(
    client,
    notebook,
    artifact,
    vault_path: Path,
    sync_state: SyncState,
    include_media: bool,
    dry_run: bool,
    verbose: bool,
) -> None
    """Route artifact to correct handler by type.
    Raises ImportItemError on failure (caught by caller)."""

async def discover_and_parse_raw(client, notebook_id: str, artifact) -> str
    """Call _list_raw(), log structure on first call, parse quiz/flashcard
    content into markdown. Runtime discovery — structure not known at design time."""

def write_note(vault_path: Path, relative_path: str, content: str) -> None
    """Create parent directories if needed. Write content to file as UTF-8."""

def write_binary(vault_path: Path, relative_path: str, data: bytes) -> None
    """Create parent directories if needed. Write binary data to file."""
```

**ImportResult dataclass:**

```python
@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)
    # Each failure: {"title": str, "type": str, "error": str}
```

**Rate limiting:** 1-second `asyncio.sleep()` between each API request.

### 6.5 Boundary Summary

```
CLI ──(function call)──► Importer ──(async)──► notebooklm-py (external API)
                              │
                              ├──(function call)──► Formatters (pure, no I/O)
                              │
                              ├──(function call)──► SyncState (filesystem I/O)
                              │
                              └──(function call)──► write_note / write_binary (filesystem I/O)
```

No network calls except through notebooklm-py. No inter-process communication. All boundaries are in-process function calls.

---

## 7. Technical Decisions

### 7.1 Language & Runtime

- **Decision:** Python 3.9+
- **Alternatives considered:** Node.js (notebooklm-py is Python-only, would require rewriting or shelling out), Rust (overkill for a CLI import tool with an existing Python library).
- **Trade-offs:** Tied to notebooklm-py's Python ecosystem. Acceptable — this tool's entire value proposition depends on that library.

### 7.2 CLI Framework

- **Decision:** Click
- **Alternatives considered:** argparse (stdlib, no dependency, but verbose for subcommands and flag validation), Typer (nicer API but adds a dependency chain including typing-extensions).
- **Trade-offs:** Click is a single well-established dependency. Subcommand routing, option parsing, and help generation are handled cleanly.

### 7.3 Async Strategy

- **Decision:** `asyncio.run()` at the CLI boundary, async throughout importer.
- **Alternatives considered:** Synchronous only (simpler, but notebooklm-py is async-native — wrapping every call in `asyncio.run()` individually is worse), full async CLI with `asyncclick` (unnecessary complexity for a sequential import tool).
- **Trade-offs:** The import loop is sequential (1-second delay between requests anyway), so async provides no parallelism benefit. We use it because the underlying library is async, not for performance.

### 7.4 Sync State Storage

- **Decision:** Single JSON file (`.notebooklm-sync.json`) at vault root.
- **Alternatives considered:** SQLite (more robust queries but overkill — we only do key lookups and full scans), per-notebook state files (more granular but harder to get a global status view), frontmatter-based tracking in each note (couples state to output files, fragile if user edits frontmatter).
- **Trade-offs:** JSON file can grow large with many notebooks/items. Acceptable — even 1,000 items produce a ~200KB file. No concurrent write safety, but single-user CLI means no concurrent writes.

### 7.5 Frontmatter Format

- **Decision:** YAML frontmatter with three note types (Literature, Resource, Inbox) as specified in the original plan document. Assumptions based on the plan's examples, pending validation against actual Obsidian vault conventions.
- **Alternatives considered:** Dataview-compatible inline fields (more flexible queries but less standard), JSON frontmatter (Obsidian doesn't render it natively).
- **Trade-offs:** If the actual vault CLAUDE.md has additional required fields or different tag conventions, the formatter output will need adjustment. The design isolates all formatting in `formatters.py`, so changes are localized.
- **⚠ Assumption flag:** The frontmatter fields (`type`, `status`, `created`, `updated`, `source`, `author`) and tag format (`#NotebookLM #Notebook_Title`) are based on the original plan document's examples. These may need revision once the vault's CLAUDE.md is reviewed.

### 7.6 Filename Sanitization

- **Decision:** Strip `/ \ : * ? " < > |`, trim whitespace, truncate to 200 characters.
- **Alternatives considered:** URL-encoding special characters (preserves more info but produces ugly filenames), replacing with hyphens (can collide: "A/B" and "A:B" both become "A-B").
- **Trade-offs:** Stripping may produce duplicate filenames in rare cases (e.g., two sources named `A:B` and `A*B` both become `AB`). Acceptable — the sync state tracks by API ID, not filename.

### 7.7 API Version Compatibility

- **Decision:** Try 0.3.x methods first, fall back to 0.1.x methods via `hasattr()` checks.
- **Alternatives considered:** Hard-require 0.3.4 only (simpler but breaks if user has older version), version-check at startup and refuse to run below 0.3.0 (cleaner but the plan document explicitly includes fallback logic).
- **Trade-offs:** `hasattr()` fallbacks add code paths that are hard to test. Acceptable — the fallback is a single method (`get_fulltext` → `get_guide`), not a pervasive pattern.

### 7.8 Quiz/Flashcard Parsing (Runtime Discovery)

- **Decision:** Call `_list_raw()`, log the raw JSON structure on first encounter, then build a parser based on discovered structure. The implementation plan will include an explicit discovery step.
- **Alternatives considered:** Pre-define a parser based on guessed structure (fragile — if wrong, everything breaks), skip quiz/flashcard import entirely (loses valuable content).
- **Trade-offs:** The parser cannot be fully designed at spec time. The implementation plan must include a task for structure discovery and a flexible parsing approach that handles unknown keys gracefully.

### 7.9 Rate Limiting

- **Decision:** Fixed 1-second `asyncio.sleep()` between each API request.
- **Alternatives considered:** Exponential backoff on 429 responses (more sophisticated but notebooklm-py's rate limits are undocumented), no delay (risks hitting unknown rate limits).
- **Trade-offs:** 1-second fixed delay makes imports slower (100 items = ~100 seconds minimum). Acceptable for a batch import tool that runs infrequently.

### 7.10 Binary File Handling (Media, Infographics, Slide Decks)

- **Decision:** Download binary to `7. Attachments/`, create a separate Resource link note in `3. Resources/` that embeds/links to the binary via Obsidian `![[filename]]` syntax.
- **Alternatives considered:** Binary only with no link note (content is invisible in graph view and search), embed binary directly in the markdown note (not possible for audio/video in Obsidian).
- **Trade-offs:** Two files per binary asset (the asset + the link note). Acceptable — this is the standard Obsidian pattern for non-markdown content.

---

## 8. Testing Strategy

All validation is manual via CLI execution and Obsidian inspection. No automated test suite.

### 8.1 Validation Sequence

Execute in order. Each step depends on the previous one passing.

| Step | Command | What to verify |
|---|---|---|
| 1. Auth | `nlm2obsidian login` | Browser opens, authentication completes, "Login successful" printed. |
| 2. List | `nlm2obsidian list` | Table prints with notebook titles, IDs, source/artifact counts. Verify against NotebookLM web UI. |
| 3. Dry run (single) | `nlm2obsidian import --notebook "테스트" --dry-run` | File path list printed. No files created in vault. No `.notebooklm-sync.json` created/modified. |
| 4. Sources only | `nlm2obsidian import --notebook "테스트" --type sources` | Literature notes created in `5. Zettelkasten/10. Literature/NotebookLM/{notebook}/`. Open in Obsidian — verify frontmatter fields, tags, content body. |
| 5. Artifacts only | `nlm2obsidian import --notebook "테스트" --type artifacts` | Reports → Literature notes. Quizzes/flashcards → Resource notes in `3. Resources/`. Binary assets → `7. Attachments/` + link notes in `3. Resources/`. |
| 6. Notes only | `nlm2obsidian import --notebook "테스트" --type notes` | User notes → Inbox notes in `5. Zettelkasten/00. Inbox/`. Chat history → single `Chat History.md` in same folder. |
| 7. Full import | `nlm2obsidian import --notebook "테스트"` | All content types imported. Counts in summary match NotebookLM web UI. |
| 8. Duplicate prevention | Run step 7 again without `--force` | All items reported as "skipped (already synced)". No new files created. Zero items imported. |
| 9. Force re-import | `nlm2obsidian import --notebook "테스트" --force` | All items re-imported. Files overwritten. Sync timestamps updated. |
| 10. Status | `nlm2obsidian status` | Table shows notebook name, item counts per type, last sync time. Matches what was imported. |
| 11. Multi-notebook | `nlm2obsidian import --notebook "all"` | All notebooks processed. Each gets its own subfolder. No cross-contamination. |
| 12. Partial match | `nlm2obsidian import --notebook "AI"` | All notebooks with "AI" in the title (case-insensitive) are imported. |
| 13. No match | `nlm2obsidian import --notebook "zzz_nonexistent"` | Error message printed. Exit code 1. No files created. |

### 8.2 Obsidian-Specific Checks

After import, open Obsidian and verify:

- **Frontmatter:** Renders correctly in Obsidian's Properties view. No YAML parse errors.
- **Tags:** Appear in Obsidian's tag pane. Clickable and filterable.
- **Internal links:** `![[attachment.mp3]]` style links resolve to correct files in Attachments.
- **Graph view:** Imported notes appear as nodes. Link notes connect to their parent notebook folder.
- **Search:** Full-text search finds content from imported sources.
- **Folder structure:** No unexpected folders created. Paths match the mapping table in Section 4.

### 8.3 Error Handling Checks

| Scenario | How to trigger | Expected behavior |
|---|---|---|
| Auth expired | Wait for token expiry, then run `import` | "Session expired. Run `nlm2obsidian login` first." Exit code 1. |
| Invalid vault path | `--vault /nonexistent/path` | "Vault path not found: /nonexistent/path" Exit code 1. |
| Single item API failure | Disconnect network mid-import (or mock) | Failed item skipped, remaining items continue, failure list printed at end. |
| Empty notebook | Import a notebook with no sources/artifacts/notes | "No content to import for {notebook}." Zero items imported, no error. |
| Filename collision | Two sources with names that sanitize to the same string | Both files written — second overwrites first. Sync state tracks both by API ID. Acceptable edge case. |

---

## 9. Open Questions

These are unresolved items that the implementer should be aware of. They do not block implementation but may require runtime decisions or post-implementation adjustment.

| # | Question | Impact | Recommended Action |
|---|---|---|---|
| 1 | **Obsidian vault CLAUDE.md rules unknown.** The actual vault may require additional frontmatter fields, different tag conventions, or specific folder naming rules beyond what the original plan document specifies. | Formatters may produce notes that don't conform to vault conventions. | Implementer should read `/Users/kpsfamily/Obsidian/CLAUDE.md` and `/Users/kpsfamily/Obsidian/5. Zettelkasten/CLAUDE.md` before writing `formatters.py`. Adjust frontmatter fields and tag format to match. |
| 2 | **Breakneck.md reference format unknown.** The Literature note "golden example" at `/Users/kpsfamily/Obsidian/5. Zettelkasten/10. Literature/독서/Breakneck.md` has not been inspected. The formatter's Literature note output may differ from the established pattern. | Literature notes may look inconsistent with hand-created notes in the vault. | Implementer should read `Breakneck.md` and use it as the template for `format_literature_note()`. |
| 3 | **`_list_raw()` return structure for quizzes/flashcards is unknown.** Parser cannot be designed until the actual JSON structure is observed. | Quiz/flashcard import may fail or produce poorly formatted notes. | Implementation plan includes an explicit discovery step: call `_list_raw()`, log output, then write parser. |
| 4 | **Chat API message structure unknown.** The chat API exists in 0.3.4 but the exact method signature and return format have not been documented in this spec. | Chat history formatting may need runtime adjustment. | Same discovery approach as #3. Implementer should call the chat API, log the response structure, then format accordingly. |
| 5 | **Mind map JSON node structure unknown.** `notes.list_mind_maps()` returns JSON, but the key names for nodes, children, and labels are not documented. | `mindmap_to_markdown()` may need adjustment after seeing real data. | Implementer should log the first mind map response and adapt the tree walker. Handle both `"children"` and `"nodes"` as possible child keys. |
| 6 | **Tag format convention.** Spec assumes `#NotebookLM #Notebook_Title` with underscores replacing spaces. The vault may use a different convention (nested tags like `#NotebookLM/notebook-name`, camelCase, lowercase, etc.). | Tags may not match existing vault conventions. | Implementer should check existing tags in the vault and match the pattern. |
| 7 | **Filename collision handling.** Current design lets the second file overwrite the first when two sources sanitize to the same filename. This is a known but unlikely edge case. | Data loss if it occurs. | If this becomes a real problem in practice, add a numeric suffix (`_2`, `_3`) on collision. Not worth building preemptively. |

---

## 10. Future Considerations

Deferred from this iteration. Documented here for context, not for implementation.

| Feature | Description | Why deferred |
|---|---|---|
| **Bidirectional sync** | Push Obsidian edits back to NotebookLM. | NotebookLM API may not support writes. Fundamentally different architecture (event-driven vs batch). |
| **Incremental update detection** | Compare content hashes to detect changes in already-synced items, re-import only changed content without `--force`. | Requires storing content hashes in sync state. Adds complexity for marginal gain — `--force` covers the use case. |
| **Obsidian plugin** | Native Obsidian community plugin with UI, settings panel, and scheduled sync. | Requires TypeScript rewrite, Obsidian plugin API knowledge, and a different distribution model. CLI-first validates the concept. |
| **Parallel API requests** | Fetch multiple sources/artifacts concurrently instead of sequential with 1-second delay. | Rate limits are undocumented. Safe sequential approach first; optimize if import speed becomes a real pain point. |
| **Template customization** | Let users define their own frontmatter templates and folder mappings via a config file. | Current hard-coded mappings match one vault. Generalize only if other users adopt the tool. |
| **Automated tests** | pytest suite for formatters, sync state, and importer logic with mocked API responses. | Manual validation is sufficient for a single-user tool in early development. Add tests if the tool grows in scope or contributors. |
| **Export/backup** | Export sync state and imported notes as a portable archive. | No immediate need. Sync state JSON is already human-readable and portable. |

---

## Appendix: Reference Files

The implementer should read these files before starting implementation:

| File | Purpose |
|---|---|
| `/Users/kpsfamily/Library/Python/3.9/lib/python/site-packages/notebooklm/types.py` | Notebook, Source, Artifact, Note dataclasses |
| `/Users/kpsfamily/Library/Python/3.9/lib/python/site-packages/notebooklm/_artifacts.py` | Artifact API (list, download, _list_raw) |
| `/Users/kpsfamily/Library/Python/3.9/lib/python/site-packages/notebooklm/_sources.py` | Source API (list, get_fulltext, get_guide) |
| `/Users/kpsfamily/Library/Python/3.9/lib/python/site-packages/notebooklm/_notes.py` | Note/mind map API |
| `/Users/kpsfamily/코딩 프로젝트/content-dashboard-agent/.claude/skills/notebooklm-ingestion/scripts/extract_notebooklm.py` | API call pattern reference (do not copy code, use as reference only) |
| `/Users/kpsfamily/Obsidian/CLAUDE.md` | Vault-level rules (frontmatter, tags, folder structure) |
| `/Users/kpsfamily/Obsidian/5. Zettelkasten/CLAUDE.md` | Zettelkasten folder-specific rules |
| `/Users/kpsfamily/Obsidian/5. Zettelkasten/10. Literature/독서/Breakneck.md` | Literature Note format reference (golden example) |
