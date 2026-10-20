import json

from niess_ditto.setup_generator import build_model

BUILDER = '''
from pathlib import Path
from mccode_antlr.loader.loader import parse_mcstas_instr

def model(name="t"):
    calls = Path(__file__).with_suffix(".calls")
    calls.write_text(str(int(calls.read_text() or 0) + 1) if calls.exists() else "1")
    return {"children": [{"name": name}]}, parse_mcstas_instr(
        f"define instrument {name}(double a=1) trace end")
'''


def test_a_model_is_built_once_and_rebuilt_when_its_options_change(tmp_path):
    builder = tmp_path / "builder.py"
    builder.write_text(BUILDER)
    calls = tmp_path / "builder.calls"
    work = tmp_path / "model"

    instrument, structure = build_model(f"{builder}:model", work)
    assert json.loads(open(structure).read()) == {"children": [{"name": "t"}]}
    assert '"t"' in open(instrument).read()
    assert build_model(f"{builder}:model", work) == (instrument, structure)
    assert calls.read_text() == "1"  # reused

    build_model(f"{builder}:model", work, name="u")
    assert calls.read_text() == "2"
    assert json.loads(open(structure).read()) == {"children": [{"name": "u"}]}

    builder.write_text(BUILDER + "\n# changed\n")
    build_model(f"{builder}:model", work, name="u")
    assert calls.read_text() == "3"


REPLAY = '''
import json
from pathlib import Path

def efus(directory):
    senders = Path(directory) / "senders.json"
    senders.write_text(json.dumps({"senders": []}))
    return {"efu": ["name:cbm,binary:/bin/cbm,config:c,calibration:c,topic:t,port:9001"],
            "senders": str(senders)}

def wrong(directory):
    return {"efus": []}
'''


def test_the_replay_builder_writes_into_its_directory_and_names_the_efus(tmp_path):
    from niess_ditto.setup_generator import build_replay
    builder = tmp_path / "replay.py"
    builder.write_text(REPLAY)
    made = build_replay(f"{builder}:efus", tmp_path / "efus")
    assert made["efu"][0].startswith("name:cbm,")
    assert json.loads(open(made["senders"]).read()) == {"senders": []}
    assert made["senders"] == str(tmp_path / "efus" / "senders.json")


def test_a_replay_builder_returning_something_else_is_refused(tmp_path):
    import pytest
    from niess_ditto.setup_generator import build_replay
    builder = tmp_path / "replay.py"
    builder.write_text(REPLAY)
    with pytest.raises(ValueError, match="not 'efu' and 'senders'"):
        build_replay(f"{builder}:wrong", tmp_path / "efus")
