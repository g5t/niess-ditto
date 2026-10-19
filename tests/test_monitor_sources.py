import pytest

from niess_ditto.setup_generator import with_monitor_sources


def _monitor(name, module="da00"):
    return {"type": "group", "name": name,
            "attributes": [{"name": "NX_class", "values": "NXmonitor"}],
            "children": [{"type": "group", "name": "data", "children": [
                {"module": module, "config": {"topic": "bifrost_beam_monitor", "source": name}}]}]}


def _source(group):
    return group["children"][0]["children"][0]["config"]["source"]


def test_a_monitor_publishes_under_the_source_given_and_keeps_its_name():
    structure = {"children": [_monitor("psc_monitor"), _monitor("overlap_monitor")]}
    out = with_monitor_sources(structure, {"psc_monitor": "cbm1"})
    assert [g["name"] for g in out["children"]] == ["psc_monitor", "overlap_monitor"]
    assert [_source(g) for g in out["children"]] == ["cbm1", "overlap_monitor"]
    assert _source(structure["children"][0]) == "psc_monitor"  # the original is untouched


def test_only_histogram_streams_are_renamed():
    structure = {"children": [_monitor("psc_monitor", module="f144")]}
    with pytest.raises(ValueError, match="psc_monitor"):
        with_monitor_sources(structure, {"psc_monitor": "cbm1"})


def test_a_monitor_the_structure_lacks_is_an_error():
    with pytest.raises(ValueError, match="psc_monitr"):
        with_monitor_sources({"children": [_monitor("psc_monitor")]}, {"psc_monitr": "cbm1"})
