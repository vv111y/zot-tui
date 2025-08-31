from zotero_tui.db import Collection, build_collection_path


def test_build_collection_path_simple():
    a = Collection(id=1, name="A", parent_id=None)
    b = Collection(id=2, name="B", parent_id=1)
    c = Collection(id=3, name="C", parent_id=2)
    allc = [a, b, c]

    assert build_collection_path(a, allc) == "/A"
    assert build_collection_path(b, allc) == "/A/B"
    assert build_collection_path(c, allc) == "/A/B/C"
