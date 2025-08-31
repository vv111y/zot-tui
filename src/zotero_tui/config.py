from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def default_zotero_db_path() -> Path:
    """Best-effort to detect Zotero sqlite path on macOS/Linux.

    Returns:
        Path to zotero.sqlite. Does not guarantee existence.
    """
    # Common macOS locations
    mac_paths = [
        Path.home() / "Zotero" / "zotero.sqlite",
        Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles",
    ]

    for p in mac_paths:
        if p.suffix == ".sqlite" and p.exists():
            return p
        if p.is_dir():
            # Find zotero.sqlite in profiles
            for child in p.rglob("zotero.sqlite"):
                return child

    # Fallback to HOME/Zotero
    return Path.home() / "Zotero" / "zotero.sqlite"


def get_db_path(override: Optional[str] = None) -> Path:
    """Resolve the sqlite DB path, optionally from env/override.

    Precedence: override arg > $ZOTERO_SQLITE > default detection.
    """
    if override:
        return Path(override).expanduser()
    env = os.getenv("ZOTERO_SQLITE")
    if env:
        return Path(env).expanduser()
    return default_zotero_db_path()
