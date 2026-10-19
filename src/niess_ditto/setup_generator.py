"""Generate the NICOS devices of a DITTO digital model.

Every numeric McStas parameter becomes a device. Those the real instrument's NICOS
setups control take the real device's name (or the one ``names`` gives it), found by
`niess_ditto.translator` from the PVs both sides name; the rest keep the parameter's
name and are hidden, for the admin. Chopper speeds and controllers become the
`niess_ditto.chopper` stand-ins, and `niess_ditto.band.IncidentBand` sets all six discs
from one incident energy.
"""
import json
from pathlib import Path

from nicos.utils import Device

#: chopcal's NICOS names for BIFROST's discs (``chopcal.nicos.NICOS_NAMES`` values)
DISCS = ("psc1", "psc2", "foc1", "foc2", "bwc1", "bwc2")


def _device(cls, **params):
    return Device((cls, params))


def _unit(parameter):
    return (parameter.unit or "").strip('"')


def _stamp(builder, options) -> str:
    """Identifies what a model built by ``builder`` with ``options`` is built from: the
    builder's source and those of niess and mccode-antlr, which may be checkouts whose
    version does not change with them."""
    import hashlib
    from importlib.util import find_spec

    import mccode_antlr
    import niess

    where = builder.rpartition(":")[0]
    files = [Path(where if where.endswith(".py") else find_spec(where).origin)]
    for package in (niess, mccode_antlr):
        root = Path(package.__file__).parent
        files += sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    digest = hashlib.sha256(json.dumps([builder, options], sort_keys=True).encode())
    for file in files:
        digest.update(str(file).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def build_model(builder, workdir, **options):
    """Build the digital model with ``builder``, or reuse the one built last time.

    ``builder`` (``"file.py:function"`` or ``"module:function"``) is called with
    ``options`` and returns the NeXus structure and the McStas instrument. Both are
    written to ``workdir``, and their paths returned, ``(instrument_json,
    structure_json)``. Building the instrument takes seconds and NICOS evaluates a setup
    in every process that reads it, so a build is kept until its stamp changes (see
    `_stamp`), and one process builds while the others wait.
    """
    import fcntl
    from mccode_antlr.io.json import save_json

    from .sample import builder_function

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    instrument, structure = workdir / "model.instr.json", workdir / "model.json"
    stamp_file, wanted = workdir / "model.stamp", _stamp(builder, options)
    with open(workdir / "model.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (stamp_file.exists() and stamp_file.read_text() == wanted
                and instrument.exists() and structure.exists()):
            built_structure, instr = builder_function(builder)(**options)
            structure.write_text(json.dumps(built_structure))
            save_json(instr, instrument)
            stamp_file.write_text(wanted)
    return str(instrument), str(structure)


def nexus_template(instrument_json, structure_json, path):
    """Write the start message's structure: the streams and links the run writes,
    with the parameters plumber adds. Its datasets are in the writer's template.
    """
    from mccode_plumber.manage.orchestrate import (
        PREFIX, TOPICS, get_instr_name_and_parameters, load_file_json,
    )
    from mccode_plumber.writer import (
        add_pvs_to_nexus_structure, construct_writer_pv_dicts_from_parameters,
    )
    from .template import without_datasets
    _, parameters = get_instr_name_and_parameters(instrument_json)
    pvs = construct_writer_pv_dicts_from_parameters(parameters, PREFIX, TOPICS["parameter"])
    structure = add_pvs_to_nexus_structure(without_datasets(load_file_json(structure_json)), pvs)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(structure))
    return str(path)


def with_monitor_sources(structure: dict, sources: dict) -> dict:
    """A copy of ``structure`` whose monitors publish under the Kafka sources given.

    ``sources`` maps an ``NXmonitor`` group's name to the source its histogram (da00)
    stream takes, as the real instrument's structure names them: ``{"psc_monitor":
    "cbm1"}``. The group keeps its name, so mccode-plumber still finds the histogram
    and publishes it under the new source.
    """
    unused = set(sources)

    def renamed(node, monitor=None):
        if isinstance(node, list):
            return [renamed(n, monitor) for n in node]
        if not isinstance(node, dict):
            return node
        classes = [a.get("values") for a in node.get("attributes") or ()
                   if isinstance(a, dict) and a.get("name") == "NX_class"]
        if "NXmonitor" in classes:
            monitor = node.get("name")
        out = {k: renamed(v, monitor) for k, v in node.items()}
        if out.get("module") == "da00" and monitor in sources:
            out["config"] = dict(out["config"], source=sources[monitor])
            unused.discard(monitor)
        return out

    out = renamed(structure)
    if unused:
        raise ValueError(f"no monitor stream to rename for {', '.join(sorted(unused))}")
    return out


def ensure_topics(broker, structure_json):
    """Create the Kafka topics the file-writer devices need before they are created.

    NICOS creates devices in name order, so ``FileWriterStatus`` comes before the
    services that would otherwise create its topic. Best effort: without a broker the
    file-writer devices fail to create, saying so, and everything else still works.
    """
    from mccode_plumber.manage.orchestrate import (
        TOPICS, get_stream_modules, load_file_json, register_topics, topics_of,
    )
    topics = list(TOPICS.values()) + topics_of(get_stream_modules(load_file_json(structure_json)))
    try:
        register_topics(broker, list(dict.fromkeys(topics)))
    except Exception as error:  # noqa: BLE001 - reported, and the setup still loads
        print(f"warning: could not create the Kafka topics at {broker}: {error}")


#: Where ESS' esslivedata devices live
LIVEDATA = "nicos_ess.devices.datasources.livedata"


def livedata_devices(real, broker, data_timeout):
    """The real instrument's esslivedata collector and its channels, for DITTO.

    The collector becomes `niess_ditto.livedata.SimLiveDataCollector`, counting on the
    proton charge preset. A channel's ``data_timeout`` must outlast a point: a monitor
    histogram arrives once, when the point has been simulated, not continuously.
    """
    collectors = {name: config for name, (cls, config) in real.items()
                  if cls == f"{LIVEDATA}.LiveDataCollector"}
    if len(collectors) != 1:
        raise ValueError(f"expected one {LIVEDATA}.LiveDataCollector in the real setups, "
                         f"found {sorted(collectors) or 'none'}")
    (name, config), = collectors.items()
    devices = {}
    for channel in [*config.get("others", ()), *config.get("timers", ())]:
        cls, channel_config = real[channel]
        if cls == f"{LIVEDATA}.DataChannel":
            channel_config = dict(channel_config, data_timeout=data_timeout)
        devices[channel] = _device(cls, **channel_config)
    devices[name] = _device("niess_ditto.livedata.SimLiveDataCollector",
                            **dict(config, brokers=[broker], monitors=["charge"]))
    return devices


def make_ditto_setup(
    instrument_json=None,
    structure_json=None,
    nicos_setups=(),
    names=None,
    broker="localhost:9092",
    workdir="/tmp/ditto",
    rays_per_charge=1.0,
    efu=(),
    sample_builder=None,
    livedata=False,
    livedata_timeout=3600.0,
    monitor_sources=None,
    model_builder=None,
    model_options=None,
):
    """Return the ``devices`` dict of a DITTO setup.

    The digital model is ``instrument_json`` and ``structure_json``, or else what
    ``model_builder`` builds with ``model_options`` (see `build_model`), into ``workdir``.

    ``nicos_setups`` are the real instrument's NICOS setup directories, read to name the
    devices. ``names`` renames any of them: ``{"sample_stack_rotation": "a3"}``.
    ``sample_builder`` (``"file.py:function"``) builds the instrument around a niess
    sample; with it, ``sim_sample.load_sample(script)`` changes the sample.
    ``livedata`` adds the real instrument's esslivedata collector and channels, which
    count each point as the real instrument would (``SetDetectors(livedata_collector)``),
    their data timeout ``livedata_timeout`` seconds.
    ``monitor_sources`` renames the Kafka sources of the monitors, by group name, as the
    real instrument's structure names them (see `with_monitor_sources`); everything
    DITTO starts uses the renamed structure, written into ``workdir``.
    """
    from mccode_antlr.common.expression import DataType
    from mccode_plumber.manage.orchestrate import get_instr_name_and_parameters, load_file_json

    from .translator import read_setups, translate

    if model_builder:
        instrument_json, structure_json = build_model(
            model_builder, Path(workdir) / "model", **(model_options or {}))
    if not (instrument_json and structure_json):
        raise ValueError("give instrument_json and structure_json, or a model_builder")
    names = dict(names or {})
    instr_name, parameters = get_instr_name_and_parameters(instrument_json)
    if monitor_sources:
        path = Path(workdir) / f"{instr_name}_structure.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            with_monitor_sources(load_file_json(structure_json), monitor_sources)))
        structure_json = str(path)
    real = read_setups(nicos_setups)
    found = translate(load_file_json(structure_json), real)
    nicos_of = {p: d for d, p in found.parameters.items()}
    speeds = set(found.controllers.values())

    def renamed(nicos_name):
        return names.get(nicos_name, nicos_name)

    devices = {
        "sim_state": _device("niess_ditto.state.SimState",
                             description=f"{instr_name} simulation state"),
    }
    fixed = {}
    for p in parameters:
        if p.value.is_str:
            if p.value.has_value:
                fixed[p.name] = str(p.value.value).strip('"')
            continue
        nicos_name = nicos_of.get(p.name)
        config = dict(
            description=f"{instr_name} {p.name}",
            state="sim_state",
            parameter=p.name,
            unit=_unit(p),
            abslimits=(-1e9, 1e9),
        )
        if nicos_name in found.negated:
            config["sign"] = -1
        if p.value.has_value:
            config["default"] = config.get("sign", 1) * p.value.value
        if p.value.data_type == DataType.int:
            config["fmtstr"] = "%d"
        if nicos_name is None:
            devices[p.name] = _device("niess_ditto.motor.SimMotor", visibility=(), **config)
        elif nicos_name in speeds:
            mapping = found.devices[nicos_name][1].get("mapping") or {}
            devices[renamed(nicos_name)] = _device(
                "niess_ditto.chopper.SimChopperSpeed",
                speeds=sorted(float(v) for v in mapping.values()), **config)
        else:
            devices[renamed(nicos_name)] = _device("niess_ditto.motor.SimMotor", **config)

    for controller, speed in found.controllers.items():
        devices[renamed(controller)] = _device(
            "niess_ditto.chopper.SimChopperController",
            description=f"{instr_name} {controller} controller", speed=renamed(speed))

    band = {f"{disc}_chopper_{what}": renamed(f"{disc}_chopper_{what}")
            for disc in DISCS for what in ("speed", "delay")}
    missing = sorted(k for k, v in band.items() if v not in devices)
    if missing:
        raise ValueError(f"no device for chopcal's {', '.join(missing)}")
    devices["incident_band"] = _device(
        "niess_ditto.band.IncidentBand",
        description=f"{instr_name} incident band, set through all six choppers",
        devices=band,
        controllers=[renamed(c) for c in found.controllers],
        pulse_delay_device="pulse_delay",
    )

    devices["sim_services"] = _device(
        "niess_ditto.service_manager.SimServiceManager",
        description=f"{instr_name} data-collection services",
        instrument=instrument_json, structure=structure_json, broker=broker,
        efu=list(efu), writer_work_dir=f"{workdir}/writer",
    )
    sample = {}
    if sample_builder:
        devices["sim_sample"] = _device(
            "niess_ditto.sample.SimSample",
            description=f"{instr_name} simulated sample",
            builder=sample_builder, base_instrument=instrument_json,
            workdir=f"{workdir}/samples",
        )
        sample = {"sample": "sim_sample"}
    devices["sim_det"] = _device(
        "niess_ditto.detector.SimDetector",
        description=f"{instr_name} digital model",
        instrument=instrument_json, structure=structure_json, broker=broker,
        state="sim_state", rays_per_charge=float(rays_per_charge),
        workdir=f"{workdir}/counts", fixed=fixed, **sample,
    )
    devices["charge"] = _device(
        "niess_ditto.detector.ChargeChannel",
        description="Count preset in proton charge", mcstas="sim_det",
    )
    devices["det"] = _device(
        "nicos.devices.mcstas.Detector",
        description=f"{instr_name} detector", mcstas="sim_det", monitors=["charge"],
    )
    if livedata:
        added = livedata_devices(real, broker, livedata_timeout)
        clash = sorted(set(added) & set(devices))
        if clash:
            raise ValueError(f"esslivedata devices clash with DITTO's: {', '.join(clash)}")
        devices.update(added)

    from mccode_plumber.manage.orchestrate import TOPICS
    ensure_topics(broker, structure_json)
    # ESS' structure provider looks itself up as "NexusStructure" and reads its alias,
    # so the structure lives behind a DeviceAlias as on the real instrument.
    devices["NexusStructure_DITTO"] = _device(
        "niess_ditto.nexus.NexusStructureFile",
        description="The NeXus structure of the digital model",
        nexus_config_path=nexus_template(instrument_json, structure_json,
                                         f"{workdir}/{instr_name}_nexus_structure.json"),
        instrument_name=instr_name,
        visibility=(), **sample,
    )
    devices["NexusStructure"] = _device(
        "nicos.devices.generic.DeviceAlias",
        alias="NexusStructure_DITTO",
        devclass="nicos_ess.devices.datasinks.nexus_structure.NexusStructureJsonFile",
    )
    devices["FileWriterStatus"] = _device(
        "nicos_ess.devices.datasinks.file_writer.FileWriterStatus",
        description="Status of the file-writer",
        brokers=[broker], statustopic=[TOPICS["command"]], unit="",
    )
    devices["FileWriterControl"] = _device(
        "niess_ditto.nexus.LocalFileWriterControlSink",
        description="Control for the file-writer",
        writer_work_dir=f"{workdir}/writer",
        brokers=[broker], pool_topic=TOPICS["pool"], instrument_topic=TOPICS["command"],
        status="FileWriterStatus", nexus="NexusStructure",
    )
    return devices
