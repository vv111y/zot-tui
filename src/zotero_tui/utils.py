from __future__ import annotations

import re
from typing import Optional


_ID_RE = re.compile(r"\[(\d+)\]")


def parse_item_id_from_line(line: str) -> Optional[int]:
    """Extract the numeric itemID from a selection line like 'Title [123]'."""
    m = _ID_RE.search(line)
    return int(m.group(1)) if m else None
