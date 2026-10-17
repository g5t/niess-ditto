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


def nexus_template(instrument_json, structure_json, path):
    """Write the structure the file-writer fills, with the parameters plumber adds.

    """
    from mccode_plumber.manage.orchestrate import (
        PREFIX, TOPICS, get_instr_name_and_parameters, load_file_json,
    )
    from mccode_plumber.writer import (
        add_pvs_to_nexus_structure, construct_writer_pv_dicts_from_parameters,
    )
    _, parameters = get_instr_name_and_parameters(instrument_json)
    pvs = construct_writer_pv_dicts_from_parameters(parameters, PREFIX, TOPICS["parameter"])
    structure = add_pvs_to_nexus_structure(load_file_json(structure_json), pvs)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(structure))
    return str(path)


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


def make_ditto_setup(
    instrument_json,
    structure_json,
    nicos_setups,
    names=None,
    broker="localhost:9092",
    workdir="/tmp/ditto",
    rays_per_charge=1.0,
    efu=(),
):
    """Return the ``devices`` dict of a DITTO setup.

    ``nicos_setups`` are the real instrument's NICOS setup directories, read to name the
    devices. ``names`` renames any of them: ``{"sample_stack_rotation": "a3"}``.
    """
    from mccode_antlr.common.expression import DataType
    from mccode_plumber.manage.orchestrate import get_instr_name_and_parameters, load_file_json

    from .translator import read_setups, translate

    names = dict(names or {})
    instr_name, parameters = get_instr_name_and_parameters(instrument_json)
    found = translate(load_file_json(structure_json), read_setups(nicos_setups))
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
        if p.value.has_value:
            config["default"] = p.value.value
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
    devices["sim_det"] = _device(
        "niess_ditto.detector.SimDetector",
        description=f"{instr_name} digital model",
        instrument=instrument_json, structure=structure_json, broker=broker,
        state="sim_state", rays_per_charge=float(rays_per_charge),
        workdir=f"{workdir}/counts", fixed=fixed,
    )
    devices["charge"] = _device(
        "niess_ditto.detector.ChargeChannel",
        description="Count preset in proton charge", mcstas="sim_det",
    )
    devices["det"] = _device(
        "nicos.devices.mcstas.Detector",
        description=f"{instr_name} detector", mcstas="sim_det", monitors=["charge"],
    )

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
        visibility=(),
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
