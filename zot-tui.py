#!/usr/bin/env python3

"""Deprecated shim for the previous prototype.

Use the new CLI instead:
  - zotero-tui all
  - zotero-tui by-collection
"""

def main() -> None:
    print("This script is deprecated. Please use the `zotero-tui` CLI (pipx install .).")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3

"""Deprecated shim for the previous prototype.

Use the new CLI instead:
    - zotero-tui all
    - zotero-tui by-collection
"""

def main() -> None:
        print("This script is deprecated. Please use the `zotero-tui` CLI (pipx install .).")


if __name__ == "__main__":
        main()

import sqlite3
from pyfzf.pyfzf import FzfPrompt

con = sqlite3.connect("/Users/will/Zotero/zotero.sqlite")
cur = con.cursor()
coll_query = cur.execute("select collectionID, collectionName, parentCollectionID from collections;")
zcollections = coll_query.fetchall()


def make_collection_string (entry):
    collection_string = ''
    if entry[2]:
        # get entry where collectionID = parentCollectionID
        collection_string = make_collection_string( next(x for x in zcollections if x[0] == entry[2]))

    collection_string+=str('/' + entry[1])
    return collection_string

def make_all_collection_strings():
    return [[x[0], make_collection_string(x)] for x in zcollections]

# make nested list of entries (id#, collection string)
colls = make_all_collection_strings()

# sort alphabetically and by length wrt collection string
colls.sort(key= lambda x: x[1])


fzf = FzfPrompt()
# fzf.prompt([x for x in range(0,10)])
sel = fzf.prompt(colls)

print(sel[0])
print(type(sel[0]))

# TODO fzf returns string rep of the sublist, need to parse or something to get collection #
item_titles_query = cur.execute(
  f"""
select itemDataValues.value
from itemDataValues
inner join itemData
    on itemData.valueID = itemDataValues.valueID
inner join collectionItems
    on collectionItems.itemID = itemData.itemID
where   itemData.fieldID = 110 AND
        collectionItems.collectionID = 326
""")

        # collectionItems.collectionID = {sel[0][0]}
ztitles = item_titles_query.fetchall()

print(ztitles)

# TODO another query, almost same as above but fieldID for attachments, and then type pdf to get file path
