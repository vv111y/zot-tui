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


def run(db_path: Optional[str] = None):
    """Interactive TUI. Keys: Ctrl-C toggle collections, Ctrl-S toggle search, Ctrl-Q quit, Ctrl-H back in collections."""
    con = _connect(db_path)
    try:
        mode = "all"  # all | by-collection | search
        while True:
            if mode == "all":
                key, next_mode = actions.ui_all(con)
            elif mode == "by-collection":
                key, next_mode = actions.ui_by_collection(con)
            else:  # search
                key, next_mode = actions.ui_query(con)

            # next_mode can explicitly switch modes
            if next_mode:
                mode = next_mode
                continue

            # Ctrl-C toggles collections mode on/off
            if key == "ctrl-c":
                mode = "by-collection" if mode != "by-collection" else "all"
                continue
            # Ctrl-S toggles query mode on/off
            if key == "ctrl-s":
                mode = "search" if mode != "search" else "all"
                continue

            # Ctrl-Q now quits
            if key == "ctrl-q":
                break

            # Exit if no selection and no key
            if key is None:
                break
    finally:
        con.close()


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context, db_path: Optional[str] = typer.Option(None, help="Path to zotero.sqlite")):
    # If a subcommand (like preview) was invoked, do nothing here
    if ctx.invoked_subcommand is None:
        run(db_path)


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
