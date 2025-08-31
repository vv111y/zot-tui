# Project TODO

This file tracks plan and progress. Keep updated as we implement.

## Goals

- Provide multiple search workflows:
  - Whole library by title
  - Collections first, then titles in selected collection
  - Later: metadata search (author, etc.)
- Show metadata preview for selected item in fzf
- Hotkey to open associated PDF
- Package for pipx install; GitHub Actions to publish to PyPI

## Tasks

- [x] Create Python package skeleton (pyproject, src/, CLI via Typer)
- [x] Implement DB access for collections, titles, attachments
- [x] Implement fzf wrapper with preview + hotkeys
- [x] Whole library workflow with preview and Ctrl-O
- [x] By-collection workflow with preview and Ctrl-O
- [x] Add README and this TODO
- [ ] Improve Zotero DB auto-detection across OSes
- [x] Robust handling of Zotero storage paths (attachments:/storage: -> absolute path)
- [ ] Add author/metadata search
- [ ] Add tests (unit for path builders, SQL queries guarded by fixtures)
- [x] Add GitHub Actions: lint/tests (CI)
- [x] Add GitHub Actions: publish on tags (requires PYPI_API_TOKEN secret)
- [ ] Package docs and usage examples (add Alt-O docs and platform notes)
- [ ] Migrate any useful logic from `zot-tui.py`, then remove it

## Notes

- Set env var ZOTERO_SQLITE to point at your database if detection fails.
- macOS tested; Linux path discovery not yet implemented.
