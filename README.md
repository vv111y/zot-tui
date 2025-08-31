# zotero-tui

fzf-powered TUI for browsing Zotero collections and opening PDFs.

Features (initial):
- Search whole library by title with preview
- Search by collection, then title with preview
- Ctrl-O to open the first attachment (macOS `open`)

Install (local dev):
- pipx install .

Usage:
- zotero-tui all
- zotero-tui by-collection

Environment:
- Set `ZOTERO_SQLITE` to the path of your `zotero.sqlite` if auto-detection fails.

License: MIT