from zotero_tui.utils import parse_item_id_from_line


def test_parse_item_id_from_line():
    assert parse_item_id_from_line("Paper Title [42]") == 42
    assert parse_item_id_from_line("No id here") is None
