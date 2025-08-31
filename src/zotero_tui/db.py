from __future__ import annotations

import sqlite3
from dataclasses import dataclass
import os
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


def search_items_by_title_or_author(con: sqlite3.Connection, q: str) -> List[Tuple[int, str]]:
    """Search items by title or author substring (case-insensitive).

    This performs a simple LIKE match on title (fieldID=110) and on creators' names.
    Returns unique (itemID, display_title) rows.
    """
    cur = con.cursor()
    like = f"%{q}%"
    cur.execute(
        """
        WITH titles AS (
            SELECT d.itemID AS itemID, v.value AS title
            FROM itemData d
            JOIN itemDataValues v ON v.valueID = d.valueID
            WHERE d.fieldID = 110
        ),
        creators_join AS (
            SELECT ic.itemID, c.lastName || ', ' || COALESCE(c.firstName,'') AS name
            FROM itemCreators ic
            JOIN creators c ON c.creatorID = ic.creatorID
        )
        SELECT DISTINCT t.itemID, t.title
        FROM titles t
        LEFT JOIN creators_join cj ON cj.itemID = t.itemID
        WHERE t.title LIKE ? COLLATE NOCASE
           OR (cj.name IS NOT NULL AND cj.name LIKE ? COLLATE NOCASE)
        ORDER BY t.title COLLATE NOCASE
        """,
        (like, like),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def fetch_attachments_for_item(con: sqlite3.Connection, item_id: int) -> List[str]:
    """Return resolved file paths for attachments of a parent item.

    Resolution rules:
    - Absolute paths are returned as-is (if they exist)
    - 'storage:filename.pdf' or 'attachments:filename.pdf' => dataDir/storage/<attachmentKey>/filename.pdf
    - 'key/filename.pdf' => dataDir/storage/key/filename.pdf
    - 'filename.pdf' (no slash) => dataDir/storage/<attachmentKey>/filename.pdf
    - Empty path => list files under dataDir/storage/<attachmentKey>
    """
    cur = con.cursor()
    cur.execute(
        """
        SELECT ia.path, i.key
        FROM itemAttachments ia
        JOIN items i ON i.itemID = ia.itemID
        WHERE ia.parentItemID = ?
        """,
        (item_id,),
    )
    rows = cur.fetchall()

    # Determine Zotero data directory from DB path
    data_dir: Optional[Path] = None
    try:
        cur.execute("PRAGMA database_list;")
        for _, name, file in cur.fetchall():
            if name == "main" and file:
                data_dir = Path(file).parent
                break
    except Exception:
        data_dir = None

    resolved: List[str] = []
    for p, akey in rows:
        p = (p or "").strip()
        # Expand env and user
        if p:
            p = os.path.expandvars(os.path.expanduser(p))
        # Absolute linked files
        if p and Path(p).is_absolute():
            if Path(p).exists():
                resolved.append(p)
            else:
                resolved.append(p)  # keep even if missing; user can see it
            continue

        # Need data_dir to build storage paths
        if data_dir is None:
            if p:
                resolved.append(p)
            continue

        storage_root = data_dir / "storage"
        cand: Optional[Path] = None

        if p.startswith("storage:") or p.startswith("attachments:"):
            rel = p.split(":", 1)[1]
            if akey:
                cand = storage_root / akey / rel
            else:
                cand = storage_root / rel
        elif "/" in p or os.sep in p:
            # Could already include the key as first path segment
            cand = storage_root / p
        else:
            # just a filename
            if akey:
                cand = storage_root / akey / p

        if cand is not None:
            if cand.exists():
                resolved.append(str(cand))
            else:
                # keep candidate string even if missing; may still open
                resolved.append(str(cand))
            continue

        # If no path or couldn't resolve, list directory under key
        if akey:
            key_dir = storage_root / akey
            if key_dir.is_dir():
                # Prefer PDFs first
                pdfs = sorted([str(pth) for pth in key_dir.iterdir() if pth.is_file() and pth.suffix.lower() == ".pdf"])
                others = sorted([str(pth) for pth in key_dir.iterdir() if pth.is_file() and pth.suffix.lower() != ".pdf"])
                resolved.extend(pdfs + others)

    return resolved


def _normalize_attachment_path(con: sqlite3.Connection, path: str) -> str:
    # Expand user home and env vars early
    path = os.path.expandvars(os.path.expanduser(path))

    # Absolute path already? return as-is
    if Path(path).is_absolute():
        return path

    scheme_split = path.split(":", 1)
    scheme = scheme_split[0] if len(scheme_split) == 2 else None
    remainder = scheme_split[1] if len(scheme_split) == 2 else path

    # Resolve Zotero data dir by DB location
    data_dir: Optional[Path] = None
    try:
        cur = con.cursor()
        cur.execute("PRAGMA database_list;")
        rows = cur.fetchall()
        for _, name, file in rows:
            if name == "main" and file:
                data_dir = Path(file).parent
                break
    except Exception:
        data_dir = None

    if scheme in {"storage", "attachments"} and data_dir is not None:
        return str((data_dir / "storage" / remainder).resolve())

    # Fallback: if we have a data_dir, try joining remainder under it
    if data_dir is not None:
        return str((data_dir / remainder).resolve())

    # Last resort: return original (expanded) string
    return path
