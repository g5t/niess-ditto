from nicos.utils import Device
from nicos.core import Param

from mccode_antlr.common.expression import DataType
from mccode_plumber.manage.orchestrate import get_instr_name_and_parameters

from .config import SimInstrumentConfig


def _device(cls, **params):
    return Device((cls, params))


def _make_config_class(string_params):
    """Dynamically create a SimInstrumentConfig subclass with parameters for each string param."""
    if not string_params:
        return None
    
    parameters = {}
    for param in string_params:
        default_value = param.value.value if param.value.has_value else ""
        parameters[param.name] = Param(
            description=f"Instrument parameter: {param.name}",
            type=str,
            settable=True,
            default=default_value,
            userparam=True,
        )
    
    # Dynamically create a subclass with these parameters
    class DynamicInstrumentConfig(SimInstrumentConfig):
        pass
    
    DynamicInstrumentConfig.parameters = parameters
    return DynamicInstrumentConfig


def make_ditto_setup(
    instrument_json,
    broker="localhost:9092",
    state_name="sim_state",
    detector_name="sim_det",
    services_name="sim_services",
    config_name="sim_config",
    rays_per_charge=1.0,
    pv_prefix="mcstas:",
):
    """Return a NICOS setup devices dict for a DITTO simulation instrument.
    
    If the instrument has string parameters, this function will dynamically create
    a SimInstrumentConfig subclass and register it in the caller's module namespace.
    The caller (setup file) must call this from the module's global scope so that
    the dynamic class can be registered correctly.
    """
    import inspect
    import sys
    
    instrument_name, parameters = get_instr_name_and_parameters(instrument_json)

    # Separate numeric and string parameters
    numeric_params = []
    string_params = []
    for parameter in parameters:
        if parameter.value.is_str:
            string_params.append(parameter)
        else:
            numeric_params.append(parameter)

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
    }

    # Create and register SimInstrumentConfig subclass if there are string parameters
    config_class_name = None
    if string_params:
        config_class = _make_config_class(string_params)
        config_class_name = f"_InstrumentConfig_{id(config_class)}"
        
        # Register the class in the caller's namespace (the setup file's __main__)
        caller_frame = inspect.currentframe().f_back
        caller_globals = caller_frame.f_globals
        caller_globals[config_class_name] = config_class
        
        # Use the registered class name in the device tuple
        devices[config_name] = Device(
            (config_class_name, {"description": f"{instrument_name} instrument configuration"})
        )

    devices[detector_name] = _device(
        "niess_ditto.detector.SimDetector",
        description=f"{instrument_name} digital model",
        mcstasprog=instrument_name,
        state=state_name,
        config=(config_name if string_params else None),
        rays_per_charge=float(rays_per_charge),
    )

    # Create SimMotor devices for numeric parameters
    for parameter in numeric_params:
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
