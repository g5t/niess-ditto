from niess_ditto.template import version, without_datasets


def _dataset(name):
    return {"module": "dataset", "config": {"name": name, "values": 1}}


def test_without_datasets_keeps_groups_streams_and_links():
    stream = {"module": "f144", "config": {"source": "pv", "topic": "t"}}
    link = {"module": "link", "config": {"name": "l", "source": "/entry/a"}}
    structure = {"children": [{
        "type": "group", "name": "entry", "attributes": [{"name": "NX_class", "values": "NXentry"}],
        "children": [_dataset("title"), stream, link, {"type": "group", "name": "sample",
                                                       "children": [_dataset("name")]}],
    }]}
    entry = without_datasets(structure)["children"][0]
    assert entry["attributes"] == structure["children"][0]["attributes"]
    assert entry["children"] == [stream, link, {"type": "group", "name": "sample", "children": []}]
    assert len(structure["children"][0]["children"]) == 4  # the original is untouched


def test_version_ignores_key_order():
    assert version({"a": 1, "b": [2]}) == version({"b": [2], "a": 1}) != version({"a": 2})
