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

# DITTO_COLLECT=1 counts with the collecting build instead: each count's detector and
# monitor rays are collected, then replayed to the detector and beam monitor EFUs that
# bifrost_phonon.py's ditto_efus describes (DITTO_EFUS points elsewhere), so the monitors
# arrive as the real beam monitor EFU's events and histograms
collect = os.environ.get("DITTO_COLLECT", "") == "1"
script = os.environ.get("DITTO_SCRIPT", "/opt/ditto/bifrost_phonon.py")

devices = make_ditto_setup(
    instrument_json=prebuilt[0],
    structure_json=prebuilt[1],
    model_builder=None if all(prebuilt) else os.environ.get(
        "DITTO_MODEL", f"{script}:ditto_model"),
    # The simulated PVs take the real names, without niess's mcstas: prefix, so that
    # esslivedata finds the logs it knows; mccode-plumber holds EPICS to this machine
    model_options={"real_pv_names": True, **({"collect": True} if collect else {})},
    # The real instrument's setups name the devices, matched to parameters by PV
    nicos_setups=[Path(nicos_ess.__file__).parent / "bifrost" / "setups"],
    broker="localhost:9092",
    workdir=os.environ.get("DITTO_WORKDIR", "/tmp/ditto"),
    sample_builder=os.environ.get("DITTO_BUILDER", f"{script}:ditto_instrument"),
    sample_builder_options={"collect": True} if collect else None,
    replay_efus=os.environ.get("DITTO_EFUS", f"{script}:ditto_efus") if collect else None,
    # The real instrument's esslivedata channels: SetDetectors(livedata_collector)
    livedata=os.environ.get("DITTO_LIVEDATA", "") == "1",
    # Live, McStas' monitor histograms publish under the beam monitor EFU's names, as in
    # ECDC's structure; collected, the EFU publishes them under those names itself
    monitor_sources=None if collect else {
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
