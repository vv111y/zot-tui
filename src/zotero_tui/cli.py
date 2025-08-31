from __future__ import annotations

import os
import re
import sys
from typing import Optional

import typer

from . import actions, config, db

app = typer.Typer(add_completion=False, help="fzf-powered Zotero TUI")


def _connect(db_path: Optional[str]):
    path = config.get_db_path(db_path)
    con = db.connect(path)
    return con


@app.command()
def all(db_path: Optional[str] = typer.Option(None, help="Path to zotero.sqlite")):
    """Search whole library by title with preview; Ctrl-O to open first attachment."""
    con = _connect(db_path)
    try:
        actions.workflow_whole_library(con)
    finally:
        con.close()


@app.command()
def by_collection(db_path: Optional[str] = typer.Option(None, help="Path to zotero.sqlite")):
    """Pick a collection then search titles in it; Ctrl-O opens first attachment."""
    con = _connect(db_path)
    try:
        actions.workflow_by_collection(con)
    finally:
        con.close()


@app.command()
def search(q: str = typer.Argument(..., help="Query substring for title/author"), db_path: Optional[str] = typer.Option(None, help="Path to zotero.sqlite")):
    """Search by title/author with preview; Ctrl-O to open first attachment."""
    con = _connect(db_path)
    try:
        actions.workflow_search_metadata(con, q)
    finally:
        con.close()


@app.command(hidden=True, name="preview")
def preview(
    db_path: Optional[str] = typer.Option(None, help="Path to zotero.sqlite"),
    line: Optional[str] = typer.Option(None, help="The fzf current line (passed as {} in --preview)"),
):
    """Internal: print preview for the current line from fzf (extracts [itemID])."""
    # fzf passes the current line via {+} or we just read stdin
    # We'll read from env FZF_PREVIEW_LINES or fallback to first stdin line
    current_line = line or os.environ.get("FZF_PREVIEW_LINES")
    if not current_line:
        data = sys.stdin.read()
        current_line = data.splitlines()[0] if data else ""

    m = re.search(r"\[(\d+)\]", current_line)
    if not m:
        return
    item_id = int(m.group(1))

    con = _connect(db_path)
    try:
        text = actions._preview_for_item_sqlite(con, item_id)  # internal helper
        print(text)
    finally:
        con.close()


def main():
    app()
