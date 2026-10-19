description = "BIFROST digital model"

# The live build of BIFROST and its NeXus structure, built when the setup loads by
# bifrost_phonon.py's ditto_model (bifrost-workflow-2609; DITTO_MODEL points elsewhere)
# and kept until the script, niess or mccode-antlr change. DITTO_INSTRUMENT and
# DITTO_STRUCTURE give a prebuilt pair instead, as `bifrost_phonon.py --live` writes.
# That script's ditto_instrument rebuilds it around another sample, for load_sample
# (DITTO_BUILDER).
import os
from pathlib import Path

import nicos_ess
from niess_ditto.setup_generator import make_ditto_setup

prebuilt = os.environ.get("DITTO_INSTRUMENT"), os.environ.get("DITTO_STRUCTURE")

devices = make_ditto_setup(
    instrument_json=prebuilt[0],
    structure_json=prebuilt[1],
    model_builder=None if all(prebuilt) else os.environ.get(
        "DITTO_MODEL", "/opt/ditto/bifrost_phonon.py:ditto_model"),
    # real_pv_names=True drops the mcstas: prefix from the simulated PVs; EPICS is held
    # to this machine either way
    model_options={"real_pv_names": False},
    # The real instrument's setups name the devices, matched to parameters by PV
    nicos_setups=[Path(nicos_ess.__file__).parent / "bifrost" / "setups"],
    broker="localhost:9092",
    workdir=os.environ.get("DITTO_WORKDIR", "/tmp/ditto"),
    sample_builder=os.environ.get("DITTO_BUILDER", "/opt/ditto/bifrost_phonon.py:ditto_instrument"),
    # The real instrument's esslivedata channels: SetDetectors(livedata_collector)
    livedata=os.environ.get("DITTO_LIVEDATA", "") == "1",
    # The monitors publish under the beam monitor EFU's names, as in ECDC's structure
    monitor_sources={
        "psc_monitor": "cbm1",
        "overlap_monitor": "cbm2",
        "bandwidth_monitor": "cbm3",
        "normalization_monitor": "cbm4",
        "elastic_monitor": "cbm5",
    },
)

startupcode = """
SetDetectors(det)
"""
