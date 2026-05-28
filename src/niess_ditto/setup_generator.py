from nicos.utils import Device

from mccode_antlr.common.expression import DataType
from mccode_plumber.manage.orchestrate import get_instr_name_and_parameters


def _device(cls, **params):
    return Device((cls, params))


def make_ditto_setup(
    instrument_json,
    broker="localhost:9092",
    state_name="sim_state",
    detector_name="sim_det",
    services_name="sim_services",
    rays_per_charge=1.0,
    pv_prefix="mcstas:",
):
    """Return a NICOS setup devices dict for a DITTO simulation instrument."""
    instrument_name, parameters = get_instr_name_and_parameters(instrument_json)

    devices = {
        state_name: _device(
            "niess_ditto.state.SimState",
            description=f"{instrument_name} simulation state",
        ),
        services_name: _device(
            "niess_ditto.service_manager.SimServiceManager",
            description=f"{instrument_name} background services",
            instrument_json=instrument_json,
            broker=broker,
            pv_prefix=pv_prefix,
        ),
        detector_name: _device(
            "niess_ditto.detector.SimDetector",
            description=f"{instrument_name} digital model",
            mcstasprog=instrument_name,
            state=state_name,
            rays_per_charge=float(rays_per_charge),
        ),
    }

    for parameter in parameters:
        if parameter.value.is_str:
            continue
        default = parameter.value.value if parameter.value.has_value else 0
        valuetype = int if parameter.value.data_type == DataType.int else float
        devices[parameter.name] = _device(
            "niess_ditto.motor.SimMotor",
            description=f"{instrument_name} simulated motor: {parameter.name}",
            state=state_name,
            unit=parameter.unit or "",
            valuetype=valuetype,
            abslimits=(-1e9, 1e9),
            default=default,
            pv_prefix=pv_prefix,
        )

    return devices
