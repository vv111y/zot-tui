# zotero-tui

fzf-powered TUI for browsing Zotero collections and opening PDFs.

Features (initial):

- Search whole library by title with preview
- Search by collection, then title with preview
- Ctrl-O to open the first attachment; Alt-O to choose among multiple
- Preview shows title, authors, date, item key, citation key, DOI, URL, and abstract
- Press Enter to open a full-page view (paged via bat/less) of the entire entry
- Missing attachments are highlighted as [missing] in bright yellow

Install (local dev):

- pipx install .

Usage:

- zotero-tui
	- Default mode: All items
	- Keys:
		- Enter: full-page view of selected entry (bat/less)
		- Ctrl-C: toggle Collections mode
		- Ctrl-S: toggle Query mode
		- Ctrl-Q: quit
		- Ctrl-H: back to Collections list when inside a collection
		- Ctrl-O: open first attachment; Alt-O: choose attachment

Environment:

- Set `ZOTERO_SQLITE` to the path of your `zotero.sqlite` if auto-detection fails.

License: MIT
