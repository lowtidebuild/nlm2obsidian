"""CLI interface for nlm2obsidian.

Subcommands: login, list, import, status.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from .sync_state import SyncState

logger = logging.getLogger("nlm2obsidian")

DEFAULT_VAULT = "/Users/kpsfamily/Obsidian"


# ------------------------------------------------------------------
# CLI group
# ------------------------------------------------------------------


@click.group()
@click.version_option(package_name="nlm2obsidian")
def main():
    """Import NotebookLM content into an Obsidian vault."""
    pass


# ------------------------------------------------------------------
# login
# ------------------------------------------------------------------


@main.command()
def login():
    """Authenticate with Google NotebookLM."""
    import subprocess

    click.echo("Opening browser for NotebookLM authentication...")
    result = subprocess.run([sys.executable, "-m", "notebooklm.cli", "login"], capture_output=False)
    if result.returncode != 0:
        # Try the direct CLI command as fallback
        subprocess.run(["notebooklm", "login"], capture_output=False)


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


@main.command("list")
def list_notebooks():
    """List all NotebookLM notebooks."""

    async def _run():
        client = await _get_client()
        async with client:
            notebooks = await client.notebooks.list()

            if not notebooks:
                click.echo("No notebooks found.")
                return

            click.echo(f"\n{'Title':<40} {'Sources':>8}  ID")
            click.echo("-" * 80)
            for nb in notebooks:
                title = nb.title[:38] if len(nb.title) > 38 else nb.title
                count = getattr(nb, "sources_count", "?")
                click.echo(f"{title:<40} {count:>8}  {nb.id}")

            click.echo(f"\nTotal: {len(notebooks)} notebook(s)")

    _run_async(_run())


# ------------------------------------------------------------------
# import
# ------------------------------------------------------------------


@main.command("import")
@click.option("--vault", type=click.Path(exists=True), default=DEFAULT_VAULT,
              help="Obsidian vault root path.")
@click.option("--notebook", required=True,
              help='Notebook name (partial match, case-insensitive) or "all".')
@click.option("--type", "content_type",
              type=click.Choice(["all", "sources", "artifacts", "notes"]),
              default="all", help="Content types to import.")
@click.option("--include-media", is_flag=True, default=False,
              help="Download audio/video binaries.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview only, no files written.")
@click.option("--force", is_flag=True, default=False,
              help="Re-import already synced items.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Verbose logging.")
def import_cmd(vault, notebook, content_type, include_media, dry_run, force, verbose):
    """Import content from NotebookLM into the Obsidian vault."""

    async def _run():
        _setup_logging(verbose)

        vault_path = Path(vault)
        sync_state = SyncState(vault_path)

        client = await _get_client()
        async with client:
            # Fetch all notebooks
            all_notebooks = await client.notebooks.list()

            if not all_notebooks:
                click.echo("No notebooks found. Run `nlm2obsidian login` first.")
                sys.exit(1)

            # Filter by --notebook
            if notebook.lower() == "all":
                matched = all_notebooks
            else:
                matched = [
                    nb for nb in all_notebooks
                    if notebook.lower() in nb.title.lower()
                ]

            if not matched:
                click.echo(f"No notebook matching '{notebook}'.")
                click.echo("Available notebooks:")
                for nb in all_notebooks:
                    click.echo(f"  - {nb.title}")
                sys.exit(1)

            click.echo(f"{'[DRY RUN] ' if dry_run else ''}Importing from {len(matched)} notebook(s)...")

            # Import each matched notebook
            from .importer import ImportResult, import_notebook

            content_types = [content_type] if content_type != "all" else ["all"]
            total = ImportResult()

            for nb in matched:
                click.echo(f"\n📓 {nb.title}")
                result = await import_notebook(
                    client=client,
                    notebook=nb,
                    vault_path=vault_path,
                    content_types=content_types,
                    sync_state=sync_state,
                    include_media=include_media,
                    dry_run=dry_run,
                    force=force,
                    verbose=verbose,
                )
                total.merge(result)

            # Print summary
            click.echo(f"\n{'=' * 40}")
            click.echo(f"Imported: {total.imported}  Skipped: {total.skipped}  Failed: {total.failed}")

            if total.failures:
                click.echo(f"\nFailures ({len(total.failures)}):")
                for f in total.failures:
                    click.echo(f"  [{f['type']}] {f['title']}: {f['error']}")

    _run_async(_run())


# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------


@main.command()
@click.option("--vault", type=click.Path(exists=True), default=DEFAULT_VAULT,
              help="Obsidian vault root path.")
def status(vault):
    """Show sync status."""
    vault_path = Path(vault)
    sync_state = SyncState(vault_path)

    summaries = sync_state.get_all_summaries()
    if not summaries:
        click.echo("No sync history found. Run `nlm2obsidian import` first.")
        return

    click.echo(f"\n{'Notebook':<35} {'Sources':>8} {'Artifacts':>10} {'Notes':>6} {'Chat':>5}  Last Sync")
    click.echo("-" * 90)

    for s in summaries:
        title = s["title"][:33] if len(s["title"]) > 33 else s["title"]
        chat = "Yes" if s["chat_synced"] else "No"
        last = s.get("last_sync") or "—"
        if last and len(last) > 19:
            last = last[:19]
        click.echo(
            f"{title:<35} {s['sources']:>8} {s['artifacts']:>10} {s['notes']:>6} {chat:>5}  {last}"
        )

    click.echo()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _get_client():
    """Create and return a NotebookLM client."""
    try:
        from notebooklm import NotebookLMClient
        return await NotebookLMClient.from_storage()
    except Exception as e:
        error_msg = str(e).lower()
        if any(w in error_msg for w in ("auth", "credential", "login", "token", "unauthorized", "cookie")):
            click.echo("Session expired or not logged in. Run `nlm2obsidian login` first.")
        else:
            click.echo(f"Failed to connect to NotebookLM: {e}")
        sys.exit(1)


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        click.echo("\nInterrupted.")
        sys.exit(130)


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.setLevel(level)
    logger.addHandler(handler)

    # Also configure the importer/raw_parser loggers
    for name in ("nlm2obsidian.importer", "nlm2obsidian.raw_parser"):
        sub = logging.getLogger(name)
        sub.setLevel(level)
        sub.addHandler(handler)
