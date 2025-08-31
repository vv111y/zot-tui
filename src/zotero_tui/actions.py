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
    # Item basics
    cur.execute(
        """
        SELECT i.key, it.typeName, i.dateAdded, i.dateModified
        FROM items i
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        WHERE i.itemID = ?
        """,
        (item_id,),
    )
    row = cur.fetchone()
    item_key = row[0] if row else ""
    item_type = row[1] if row else ""
    date_added = row[2] if row else ""
    date_modified = row[3] if row else ""
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

    # Fetch all fields for the item
    field_rows: List[tuple[str, str]] = []
    try:
        cur.execute(
            """
            SELECT f.fieldName, v.value
            FROM itemData d
            JOIN itemDataValues v ON v.valueID = d.valueID
            JOIN fields f ON f.fieldID = d.fieldID
            WHERE d.itemID = ?
            ORDER BY f.fieldName
            """,
            (item_id,),
        )
        field_rows = [(name, val) for (name, val) in cur.fetchall() if val is not None]
    except Exception:
        field_rows = []

    fieldmap = {name: val for (name, val) in field_rows}

    # Try to locate a citation key (Better BibTeX) if present
    citekey = ""
    extra = fieldmap.get("extra") or ""
    if fieldmap.get("citationKey"):
        citekey = (fieldmap.get("citationKey") or "").strip()
    elif fieldmap.get("tex.citekey"):
        citekey = (fieldmap.get("tex.citekey") or "").strip()
    elif extra:
        m = re.search(r"(?:Citation Key|citekey|tex\.citekey)\s*:?\s*(\S+)", extra, re.IGNORECASE)
        if m:
            citekey = m.group(1)

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
    creators_rows = cur.fetchall()
    creators = [
        f"{ln}, {fn}" if fn else ln
        for (ln, fn) in creators_rows if (ln or fn)
    ]
    # Creators by role
    cur.execute(
        """
        SELECT ct.creatorType, c.lastName, c.firstName
        FROM itemCreators ic
        JOIN creators c ON c.creatorID = ic.creatorID
        JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex
        """,
        (item_id,),
    )
    creators_by_role: dict[str, List[str]] = {}
    for role, ln, fn in cur.fetchall():
        name = f"{ln}, {fn}" if fn else (ln or fn or "")
        if not name:
            continue
        creators_by_role.setdefault(role, []).append(name)

    # Pull commonly useful fields
    doi = (fieldmap.get("DOI") or "").strip()
    url = (fieldmap.get("url") or "").strip()
    abstract = (fieldmap.get("abstractNote") or "").strip()

    # Tags
    tags: List[str] = []
    try:
        cur.execute(
            """
            SELECT t.name
            FROM tags t
            JOIN itemTags it ON it.tagID = t.tagID
            WHERE it.itemID = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (item_id,),
        )
        tags = [r[0] for r in cur.fetchall() if r and r[0]]
    except Exception:
        tags = []

    # Collections for this item (paths)
    collections_paths: List[str] = []
    try:
        cur.execute("SELECT collectionID FROM collectionItems WHERE itemID = ?", (item_id,))
        coll_ids = [r[0] for r in cur.fetchall()]
        if coll_ids:
            all_colls = db.fetch_collections(con)
            by_id = {c.id: c for c in all_colls}
            for cid in coll_ids:
                c = by_id.get(cid)
                if c:
                    collections_paths.append(db.build_collection_path(c, all_colls))
    except Exception:
        collections_paths = []

    # attachments
    attachments = db.fetch_attachments_for_item(con, item_id)

    # Build preview text lines
    author_str = "; ".join(creators) if creators else "-"
    lines: List[str] = [
        f"Title: {title}",
        (f"Item Type: {item_type}" if item_type else "Item Type: -"),
        f"Authors: {author_str}",
        f"Date: {date_val}",
        f"Item Key: {item_key}",
        (f"Citekey: {citekey}" if citekey else "Citekey: -"),
        (f"Added: {date_added}" if date_added else "Added: -"),
        (f"Modified: {date_modified}" if date_modified else "Modified: -"),
        f"DOI: {doi if doi else '-'}",
        f"URL: {url if url else '-'}",
        "",
        "Creators:",
    ]
    if creators_by_role:
        for role, names in creators_by_role.items():
            lines.append(f"  - {role}: {', '.join(names)}")
    else:
        lines.append("  - (none)")
    lines += ["", "Tags:"]
    if tags:
        lines.append("  - " + ", ".join(tags))
    else:
        lines.append("  - (none)")
    lines += ["", "Collections:"]
    if collections_paths:
        for p in collections_paths:
            lines.append(f"  - {p}")
    else:
        lines.append("  - (none)")
    lines += ["", "All fields:"]
    if field_rows:
        for name, val in field_rows:
            lines.append(f"  - {name}: {val}")
    else:
        lines.append("  - (none)")
    lines += ["", "Attachments:"]
    if attachments:
        for p in attachments:
            exists = Path(p).exists()
            mark = "" if exists else " [\x1b[93mmissing\x1b[0m]"
            suffix = "/" if Path(p).is_dir() else ""
            lines.append(f"  - {p}{suffix}{mark}")
    else:
        lines.append("  - (none)")
    # Abstract at the end
    lines.append("")
    lines.append("Abstract:")
    if abstract:
        lines.append(abstract)
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
    header = "Mode: All  |  Ctrl-C: Collections  Ctrl-S: Query  Ctrl-Q: Quit  Ctrl-O: Open  Alt-O: Choose"
    key, selection = prompt(
        lines,
        preview_command="zotero-tui preview --line {}",
        expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-c", "ctrl-s", "ctrl-q"],
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
        header = "Mode: Collections  |  Ctrl-C: All  Ctrl-S: Query  Ctrl-Q: Quit  Enter: Select Collection"
        key, sel = prompt(col_lines, expect_keys=["enter", "ctrl-c", "ctrl-s", "ctrl-q"], header=header)
        if not sel:
            return key, None
        chosen_coll_id = parse_item_id_from_line(sel[0])
        if chosen_coll_id is None:
            return key, None

        # Items in collection
        while True:
            items = db.fetch_item_titles_in_collection(con, chosen_coll_id)
            item_lines: List[str] = [f"{title} \x1b[90m[{iid}]\x1b[0m" for iid, title in items]
            header_items = "Mode: Collection Items  |  Ctrl-H: Back to Collections  Ctrl-C: All  Ctrl-S: Query  Ctrl-Q: Quit"
            key2, item_sel = prompt(
                item_lines,
                preview_command="zotero-tui preview --line {}",
                expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-h", "ctrl-c", "ctrl-s", "ctrl-q"],
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
    header = "Mode: Query  |  Ctrl-C: Collections  Ctrl-S: All  Ctrl-Q: Quit  Ctrl-O: Open  Alt-O: Choose"
    key, selection = prompt(
        lines,
        preview_command="zotero-tui preview --line {}",
        expect_keys=["enter", "ctrl-o", "alt-o", "ctrl-c", "ctrl-s", "ctrl-q"],
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
