from __future__ import annotations

import os
import shlex
from typing import List, Optional, Sequence, Tuple

from pyfzf.pyfzf import FzfPrompt


def _build_fzf_options(preview_command: Optional[str] = None, expect_keys: Optional[Sequence[str]] = None) -> str:
    tokens: List[str] = ["--ansi", "--multi", "--height", "80%", "--border", "--layout=reverse"]
    if preview_command:
        # Quote the preview command so fzf treats it as one argument
        tokens += ["--preview", shlex.quote(preview_command)]
        tokens += ["--preview-window", "right:60%:wrap"]
    if expect_keys:
        tokens += [f"--expect={','.join(expect_keys)}"]
    return " ".join(tokens)


def prompt(entries: Sequence[str], preview_command: Optional[str] = None, expect_keys: Optional[Sequence[str]] = None) -> Tuple[Optional[str], List[str]]:
    """Prompt with fzf and optional preview and hotkeys.

    Returns a tuple (pressed_key, selected_lines).
    pressed_key is None when Enter was used without --expect.
    """
    fzf = FzfPrompt()
    options = _build_fzf_options(preview_command=preview_command, expect_keys=expect_keys)

    # Neutralize user's FZF_DEFAULT_OPTS to avoid malformed values affecting our run
    old_env = os.environ.pop("FZF_DEFAULT_OPTS", None)
    try:
        res = fzf.prompt(entries, fzf_options=options)
    finally:
        if old_env is not None:
            os.environ["FZF_DEFAULT_OPTS"] = old_env

    if expect_keys:
        # When --expect is used, pyfzf returns [key, selection1, selection2, ...]
        if not res:
            return None, []
        key = res[0] if res and res[0] in (expect_keys or []) else None
        selections = res[1:] if key else res
        return key, selections
    else:
        return None, res
