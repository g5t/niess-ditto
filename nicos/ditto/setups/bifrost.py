description = "BIFROST digital model"

# The live build of BIFROST (bifrost_phonon.py --live in bifrost-workflow-2609) and its
# NeXus structure; DITTO_INSTRUMENT and DITTO_STRUCTURE point elsewhere. That script's
# ditto_instrument rebuilds it around another sample, for load_sample (DITTO_BUILDER).
import os
from pathlib import Path

import nicos_ess
from niess_ditto.setup_generator import make_ditto_setup

devices = make_ditto_setup(
    instrument_json=os.environ.get("DITTO_INSTRUMENT", "/opt/ditto/bifrost_live.instr.json"),
    structure_json=os.environ.get("DITTO_STRUCTURE", "/opt/ditto/bifrost_live.json"),
    # The real instrument's setups name the devices, matched to parameters by PV
    nicos_setups=[Path(nicos_ess.__file__).parent / "bifrost" / "setups"],
    broker="localhost:9092",
    workdir=os.environ.get("DITTO_WORKDIR", "/tmp/ditto"),
    sample_builder=os.environ.get("DITTO_BUILDER", "/opt/ditto/bifrost_phonon.py:ditto_instrument"),
    # The real instrument's esslivedata channels: SetDetectors(livedata_collector)
    livedata=os.environ.get("DITTO_LIVEDATA", "") == "1",
)

startupcode = """
SetDetectors(det)
"""
