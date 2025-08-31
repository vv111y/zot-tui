from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from . import db
from .fzf_ui import prompt


def _preview_for_item_sqlite(con, item_id: int) -> str:
    """Render a plain-text metadata preview for an item."""
    # Fetch title (field 110) and maybe creators and year
    cur = con.cursor()
    cur.execute(
        """
        SELECT v.value AS title
        FROM itemData d
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE d.itemID = ? AND d.fieldID = 110
        """,
        (item_id,),
    )
    title = cur.fetchone()
    title = title[0] if title else "(untitled)"

    # Year fieldID is 14 (Date) – simplified extract
    cur.execute(
        """
        SELECT v.value
        FROM itemData d
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE d.itemID = ? AND d.fieldID = 14
        """,
        (item_id,),
    )
    date_val = cur.fetchone()
    date_val = date_val[0] if date_val else ""

    # creators (authors)
    cur.execute(
        """
        SELECT c.lastName, c.firstName
        FROM creators c
        JOIN itemCreators ic ON ic.creatorID = c.creatorID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex
        """,
        (item_id,),
    )
    creators = [
        f"{ln}, {fn}" if fn else ln
        for (ln, fn) in cur.fetchall() if (ln or fn)
    ]

    # attachments
    attachments = db.fetch_attachments_for_item(con, item_id)

    # Build preview text lines
    author_str = "; ".join(creators) if creators else "-"
    lines: List[str] = [
        f"Title: {title}",
        f"Authors: {author_str}",
        f"Date: {date_val}",
        "",
        "Attachments:",
    ]
    if attachments:
        lines.extend([f"  - {p}" for p in attachments])
    else:
        lines.append("  - (none)")
    return "\n".join(lines)


def workflow_whole_library(con) -> Optional[int]:
    """fzf across all item titles; preview shows metadata; return chosen itemID."""
    items = db.fetch_items_fulltext(con)
    id_by_line: Dict[str, int] = {}
    lines: List[str] = []
    for iid, title in items:
        line = f"{title} \x1b[90m[{iid}]\x1b[0m"
        lines.append(line)
        id_by_line[line] = iid

    # Build preview command by invoking this module via Python to print preview for the selected line
    # Use our own console preview helper (added in cli.py) to render metadata by item ID
    # The script will parse the [itemID] from the selected line.
    preview_cmd = "zotero-tui preview --line {}"

    key, selection = prompt(lines, preview_command=preview_cmd, expect_keys=["enter", "ctrl-o"])  # ctrl-o to open
    if not selection:
        return None
    chosen_line = selection[0]
    item_id = id_by_line[chosen_line]
    # If ctrl-o pressed, try to open first attachment
    if key == "ctrl-o":
        atts = db.fetch_attachments_for_item(con, item_id)
        if atts:
            _open_path_mac(atts[0])
    return item_id


def workflow_by_collection(con) -> Optional[int]:
    """Pick a collection, then pick an item within it. Return itemID."""
    colls = db.fetch_collections(con)
    lines: List[str] = []
    id_by_line: Dict[str, int] = {}
    for c in colls:
        path = db.build_collection_path(c, colls)
        line = f"{path} \x1b[90m[{c.id}]\x1b[0m"
        lines.append(line)
        id_by_line[line] = c.id

    key, sel = prompt(lines)
    if not sel:
        return None
    chosen_coll_id = id_by_line[sel[0]]

    # Now list items in this collection
    items = db.fetch_item_titles_in_collection(con, chosen_coll_id)
    item_lines: List[str] = []
    item_id_by_line: Dict[str, int] = {}
    for iid, title in items:
        line = f"{title} \x1b[90m[{iid}]\x1b[0m"
        item_lines.append(line)
        item_id_by_line[line] = iid

    # Reuse the same preview command
    preview_cmd = "zotero-tui preview --line {}"

    key, item_sel = prompt(item_lines, preview_command=preview_cmd, expect_keys=["enter", "ctrl-o"])
    if not item_sel:
        return None
    chosen_item_id = item_id_by_line[item_sel[0]]
    if key == "ctrl-o":
        atts = db.fetch_attachments_for_item(con, chosen_item_id)
        if atts:
            _open_path_mac(atts[0])
    return chosen_item_id


def _open_path_mac(path: str) -> None:
    # Best effort: if it's a zotero storage URI like attachments:abc.pdf, just hand off to 'open'
    os.system(f"open {Path(path).as_posix()!s}")
