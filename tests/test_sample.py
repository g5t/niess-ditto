from types import SimpleNamespace as NS

from niess_ditto.sample import nxsample, put_sample, unsettable_parameters


def test_nxsample_values_units_and_nodes():
    node = {"module": "link", "config": {"name": "depends_on", "source": "/entry/x"}}
    group = nxsample({"name": "V", "radius": (0.005, "m"), "depends_on": node})
    assert group["name"] == "sample" and group["attributes"][0]["values"] == "NXsample"
    name, radius, link = group["children"]
    assert name["config"] == {"name": "name", "values": "V", "dtype": "string"}
    assert radius["config"]["dtype"] == "double" and radius["attributes"][0]["values"] == "m"
    assert link is node


def _parameter(name, has_value):
    return NS(name=name, value=NS(has_value=has_value))


def test_only_new_parameters_without_defaults_are_unsettable():
    base = NS(parameters=[_parameter("a3", True)])
    instr = NS(parameters=[_parameter("a3", False), _parameter("t", True), _parameter("x", False)])
    assert unsettable_parameters(instr, base) == ["x"]


def test_sample_depends_on_the_frame_at_the_sample():
    link = {"module": "link", "config": {"name": "depends_on", "source": "/entry/f/depends_on"}}
    entry = {"name": "entry", "children": [{"name": "sample", "children": [], "old": True}]}
    group = put_sample(entry, nxsample({"name": "V"}), "/entry/f")
    assert entry["children"] == [group] and group["children"][-1] == link
    own = {"module": "dataset", "config": {"name": "depends_on", "values": "/elsewhere"}}
    group = put_sample(entry, nxsample({"depends_on": own}), "/entry/f")
    assert group["children"] == [own]
    entry = {"name": "entry", "children": []}
    group = put_sample(entry, None, "/entry/f")
    assert group["attributes"][0]["values"] == "NXsample" and group["children"] == [link]
