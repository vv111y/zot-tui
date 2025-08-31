from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


@dataclass
class Collection:
    id: int
    name: str
    parent_id: Optional[int]


def connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def get_db_path_for_connection(con: sqlite3.Connection) -> Optional[Path]:
    try:
        cur = con.cursor()
        cur.execute("PRAGMA database_list;")
        rows = cur.fetchall()
        for seq, name, file in rows:
            if name == "main" and file:
                return Path(file)
    except Exception:
        return None
    return None


def fetch_collections(con: sqlite3.Connection) -> List[Collection]:
    cur = con.cursor()
    cur.execute(
        """
        SELECT collectionID, collectionName, parentCollectionID
        FROM collections
        ORDER BY collectionName COLLATE NOCASE
        """
    )
    rows = cur.fetchall()
    return [Collection(id=r[0], name=r[1], parent_id=r[2]) for r in rows]


def build_collection_path(coll: Collection, all_colls: Sequence[Collection]) -> str:
    by_id = {c.id: c for c in all_colls}
    parts: List[str] = []
    current: Optional[Collection] = coll
    while current is not None:
        parts.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return "/" + "/".join(reversed(parts))


def fetch_item_titles_in_collection(con: sqlite3.Connection, collection_id: int) -> List[Tuple[int, str]]:
    """Return (itemID, title) for items in a collection.

    fieldID 110 is Zotero's Title.
    """
    cur = con.cursor()
    cur.execute(
        """
        SELECT itemData.itemID, itemDataValues.value AS title
        FROM itemData
        JOIN itemDataValues ON itemData.valueID = itemDataValues.valueID
        JOIN collectionItems ON collectionItems.itemID = itemData.itemID
        WHERE itemData.fieldID = 110
          AND collectionItems.collectionID = ?
        ORDER BY itemDataValues.value COLLATE NOCASE
        """,
        (collection_id,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def fetch_items_fulltext(con: sqlite3.Connection) -> List[Tuple[int, str]]:
    """Optional: fetch titles for all items in the library (no collection filter)."""
    cur = con.cursor()
    cur.execute(
        """
        SELECT itemData.itemID, itemDataValues.value AS title
        FROM itemData
        JOIN itemDataValues ON itemData.valueID = itemDataValues.valueID
        WHERE itemData.fieldID = 110
        ORDER BY itemDataValues.value COLLATE NOCASE
        """
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def fetch_attachments_for_item(con: sqlite3.Connection, item_id: int) -> List[str]:
    """Return file paths for PDF attachments of a given parent item.

    This uses itemAttachments, items, and itemData to retrieve local file paths.
    Zotero stores paths like 'attachments:xyz.pdf' or absolute paths in itemAttachments.path.
    """
    cur = con.cursor()
    # itemAttachments contains child items (attachments) referencing parent item
    cur.execute(
        """
        SELECT ia.path
        FROM itemAttachments ia
        JOIN items i ON i.itemID = ia.itemID
        WHERE ia.parentItemID = ?
        """,
        (item_id,),
    )
    paths = []
    for (p,) in cur.fetchall():
        if not p:
            continue
        paths.append(_normalize_attachment_path(con, p))
    return paths


def _normalize_attachment_path(con: sqlite3.Connection, path: str) -> str:
    # Zotero often uses 'attachments:' scheme; map it under dataDir/storage
    # Get Zotero data dir by looking at the DB file path and going up to its parent
    try:
        cur = con.cursor()
        cur.execute("PRAGMA database_list;")
        rows = cur.fetchall()
        main_file = None
        for _, name, file in rows:
            if name == "main":
                main_file = file
                break
        if main_file:
            db_path = Path(main_file)
            data_dir = db_path.parent
            if path.startswith("attachments:"):
                rel = path.split(":", 1)[1]
                storage = data_dir / "storage" / rel
                return str(storage)
    except Exception:
        pass
    return path
