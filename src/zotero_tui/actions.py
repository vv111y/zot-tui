from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from . import db
from .fzf_ui import prompt
from .utils import parse_item_id_from_line


def _preview_for_item_sqlite(con, item_id: int) -> str:
    """Render a plain-text metadata preview for an item."""
    # Fetch title (field 110) and maybe creators and year
    cur = con.cursor()
    # Item key
    cur.execute("SELECT key FROM items WHERE itemID = ?", (item_id,))
    item_key_row = cur.fetchone()
    item_key = item_key_row[0] if item_key_row else ""
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

    # Try to locate a citation key (Better BibTeX) if present
    citekey = ""
    try:
        cur.execute(
            """
            SELECT v.value, f.fieldName
            FROM itemData d
            JOIN itemDataValues v ON v.valueID = d.valueID
            JOIN fields f ON f.fieldID = d.fieldID
            WHERE d.itemID = ? AND f.fieldName IN ('citationKey','tex.citekey','extra')
            """,
            (item_id,),
        )
        rows = cur.fetchall()
        fieldmap = {name: val for (val, name) in rows}
        if "citationKey" in fieldmap:
            citekey = fieldmap["citationKey"].strip()
        elif "tex.citekey" in fieldmap:
            citekey = fieldmap["tex.citekey"].strip()
        elif "extra" in fieldmap:
            # Heuristics to parse from the Extra field
            extra = fieldmap["extra"]
            m = re.search(r"(?:Citation Key|citekey|tex\.citekey)\s*:?\s*(\S+)", extra, re.IGNORECASE)
            if m:
                citekey = m.group(1)
    except Exception:
        pass

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
        f"Item Key: {item_key}",
        (f"Citekey: {citekey}" if citekey else "Citekey: -"),
        "",
        "Attachments:",
    ]
    if attachments:
        for p in attachments:
            exists = Path(p).exists()
            mark = "" if exists else " [missing]"
            suffix = "/" if Path(p).is_dir() else ""
            lines.append(f"  - {p}{suffix}{mark}")
    else:
        lines.append("  - (none)")
    return "\n".join(lines)


def workflow_whole_library(con) -> Optional[int]:
    """fzf across all item titles; preview shows metadata; return chosen itemID."""
    items = db.fetch_items_fulltext(con)
    lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]

    # Build preview command by invoking this module via Python to print preview for the selected line
    # Use our own console preview helper (added in cli.py) to render metadata by item ID
    # The script will parse the [itemID] from the selected line.
    preview_cmd = "zotero-tui preview --line {}"

    key, selection = prompt(lines, preview_command=preview_cmd, expect_keys=["enter", "ctrl-o", "alt-o"])  # ctrl/alt-o to open
    if not selection:
        return None
    chosen_line = selection[0]
    item_id = parse_item_id_from_line(chosen_line)
    if item_id is None:
        return None
    # If open key pressed, open attachments
    if key in ("ctrl-o", "alt-o"):
        atts = db.fetch_attachments_for_item(con, item_id)
        existing = [p for p in atts if Path(p).exists()]
        if existing:
            if key == "alt-o" and len(existing) > 1:
                _, choose = prompt(existing, header="Choose attachment to open")
                if choose:
                    _open_path(choose[0])
            else:
                _open_path(existing[0])
        else:
            print("Attachment missing")
    return item_id


def workflow_by_collection(con) -> Optional[int]:
    """Pick a collection, then pick an item within it. Return itemID."""
    colls = db.fetch_collections(con)
    lines: List[str] = []
    for c in colls:
        path = db.build_collection_path(c, colls)
        line = f"{path} \x1b[90m[{c.id}]\x1b[0m"
        lines.append(line)
    # No mapping needed; parse back the [id]

    key, sel = prompt(lines)
    if not sel:
        return None
    chosen_coll_id = parse_item_id_from_line(sel[0])
    if chosen_coll_id is None:
        return None

    # Now list items in this collection
    items = db.fetch_item_titles_in_collection(con, chosen_coll_id)
    item_lines: List[str] = []
    for iid, title in items:
        line = f"{title} \x1b[90m[{iid}]\x1b[0m"
        item_lines.append(line)

    # Reuse the same preview command
    preview_cmd = "zotero-tui preview --line {}"

    key, item_sel = prompt(item_lines, preview_command=preview_cmd, expect_keys=["enter", "ctrl-o", "alt-o"]) 
    if not item_sel:
        return None
    chosen_item_id = parse_item_id_from_line(item_sel[0])
    if chosen_item_id is None:
        return None
    if key in ("ctrl-o", "alt-o"):
        atts = db.fetch_attachments_for_item(con, chosen_item_id)
        existing = [p for p in atts if Path(p).exists()]
        if existing:
            if key == "alt-o" and len(existing) > 1:
                _, choose = prompt(existing, header="Choose attachment to open")
                if choose:
                    _open_path(choose[0])
            else:
                _open_path(existing[0])
        else:
            print("Attachment missing")
    return chosen_item_id


def _open_path(path: str) -> None:
    # Cross-platform opener that avoids shell quoting issues
    p = Path(path)
    # If a directory was given, prefer opening a PDF inside
    if p.is_dir():
        pdfs = sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() == ".pdf"])
        others = sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() != ".pdf"])
        choices = [str(x) for x in (pdfs + others)]
        if choices:
            # prompt to choose
            _, sel = prompt(choices, header="Choose file to open")
            if sel:
                _open_path(sel[0])
            return
        # fallthrough: open directory itself
    p_str = str(p)
    if os.name == "posix":
        # distinguish macOS vs Linux by platform
        import platform
        if platform.system() == "Darwin":
            subprocess.run(["open", p_str], check=False)
        else:
            subprocess.run(["xdg-open", p_str], check=False)
    elif os.name == "nt":
        try:
            os.startfile(p_str)  # type: ignore[attr-defined]
        except Exception:
            subprocess.run(["cmd", "/c", "start", "", p_str], shell=True, check=False)
    else:
        subprocess.run(["open", p_str], check=False)


def workflow_search_metadata(con, query: str) -> Optional[int]:
    """Search by title/author substrings with preview; Ctrl-O to open PDF."""
    items = db.search_items_by_title_or_author(con, query)
    lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]

    key, selection = prompt(lines, preview_command="zotero-tui preview --line {}", expect_keys=["enter", "ctrl-o"])
    if not selection:
        return None
    item_id = parse_item_id_from_line(selection[0])
    if item_id is None:
        return None
    if key == "ctrl-o":
        atts = db.fetch_attachments_for_item(con, item_id)
        existing = [p for p in atts if Path(p).exists()]
        if existing:
            _open_path(existing[0])
        else:
            print("Attachment missing")
    return item_id


# UI loops returning (key, next_mode)
def ui_all(con) -> tuple[Optional[str], Optional[str]]:
    items = db.fetch_items_fulltext(con)
    lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]
    header = "Mode: All  |  Ctrl-C: Collections  Ctrl-Q: Query  Ctrl-O: Open  Alt-O: Choose"
    key, selection = prompt(
        lines,
        preview_command="zotero-tui preview --line {}",
        expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-c", "ctrl-q"],
        header=header,
    )
    if not selection:
        return key, None
    item_id = parse_item_id_from_line(selection[0])
    if item_id is None:
        return key, None
    if key in ("ctrl-o", "alt-o"):
        atts = db.fetch_attachments_for_item(con, item_id)
        existing = [p for p in atts if Path(p).exists()]
        if existing:
            if key == "alt-o" and len(existing) > 1:
                _, choose = prompt(existing, header="Choose attachment to open")
                if choose:
                    _open_path(choose[0])
            else:
                _open_path(existing[0])
        else:
            print("Attachment missing")
    return key, None


def ui_by_collection(con) -> tuple[Optional[str], Optional[str]]:
    while True:
        colls = db.fetch_collections(con)
        col_lines: List[str] = []
        for c in colls:
            path = db.build_collection_path(c, colls)
            col_lines.append(f"{path} \x1b[90m[{c.id}]\x1b[0m")
        header = "Mode: Collections  |  Ctrl-C: All  Ctrl-Q: Query  Enter: Select Collection"
        key, sel = prompt(col_lines, expect_keys=["enter", "ctrl-c", "ctrl-q"], header=header)
        if not sel:
            return key, None
        chosen_coll_id = parse_item_id_from_line(sel[0])
        if chosen_coll_id is None:
            return key, None

        # Items in collection
        while True:
            items = db.fetch_item_titles_in_collection(con, chosen_coll_id)
            item_lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]
            header_items = "Mode: Collection Items  |  Ctrl-H: Back to Collections  Ctrl-C: All  Ctrl-Q: Query"
            key2, item_sel = prompt(
                item_lines,
                preview_command="zotero-tui preview --line {}",
                expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-h", "ctrl-c", "ctrl-q"],
                header=header_items,
            )
            if not item_sel:
                return key2, None
            if key2 == "ctrl-h":
                break  # back to collections list

            chosen_item_id = parse_item_id_from_line(item_sel[0])
            if chosen_item_id is None:
                return key2, None
            if key2 in ("ctrl-o", "alt-o"):
                atts = db.fetch_attachments_for_item(con, chosen_item_id)
                existing = [p for p in atts if Path(p).exists()]
                if existing:
                    if key2 == "alt-o" and len(existing) > 1:
                        _, choose = prompt(existing, header="Choose attachment to open")
                        if choose:
                            _open_path(choose[0])
                    else:
                        _open_path(existing[0])
                else:
                    print("Attachment missing")

            # Return to CLI loop for potential mode toggle handling
            return key2, None


def ui_query(con) -> tuple[Optional[str], Optional[str]]:
    try:
        query = input("Query (title/author): ").strip()
    except EOFError:
        return None, None
    if not query:
        return None, None
    items = db.search_items_by_title_or_author(con, query)
    lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]
    header = "Mode: Query  |  Ctrl-C: Collections  Ctrl-Q: All  Ctrl-O: Open  Alt-O: Choose"
    key, selection = prompt(
        lines,
        preview_command="zotero-tui preview --line {}",
        expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-c", "ctrl-q"],
        header=header,
    )
    if not selection:
        return key, None
    item_id = parse_item_id_from_line(selection[0])
    if item_id is None:
        return key, None
    if key in ("ctrl-o", "alt-o"):
        atts = db.fetch_attachments_for_item(con, item_id)
        existing = [p for p in atts if Path(p).exists()]
        if existing:
            if key == "alt-o" and len(existing) > 1:
                _, choose = prompt(existing, header="Choose attachment to open")
                if choose:
                    _open_path(choose[0])
            else:
                _open_path(existing[0])
    return key, None
