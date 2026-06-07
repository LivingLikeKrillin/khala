from khala.ingest.sources.base import ConvertedDoc, DocumentSource, PageRef


def test_types_and_protocol():
    ref = PageRef(id="p1", url="https://notion.so/p1", last_edited="2026-06-06T00:00:00Z")
    cd = ConvertedDoc(page_id="p1", markdown="# t", frontmatter={"title": "t"}, image_count=2)
    assert ref.id == "p1" and cd.image_count == 2

    class Dummy:
        def list_changed(self, since):
            return []

        def fetch_markdown(self, ref):
            return ConvertedDoc(ref.id, "", {}, 0)

        def live_ids(self):
            return set()

    assert isinstance(Dummy(), DocumentSource)  # runtime_checkable
