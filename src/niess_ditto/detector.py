from nicos.core import Attach, Override, Param, floatrange
from nicos.devices.mcstas import McStasSimulation

from .state import SimState


class SimDetector(McStasSimulation):
    """McStas binary runner for DITTO digital models."""

    attached_devices = {
        "state": Attach("Shared simulation state", SimState),
        "config": Attach(
            "Instrument configuration (string parameters)",
            required=False,
        ),
    }

    parameters = {
        "rays_per_charge": Param(
            "Conversion factor from charge preset to simulated rays (-n argument)",
            type=floatrange(1e-10),
            settable=True,
            default=1.0,
            unit="rays/charge_unit",
        ),
    }

    parameter_overrides = {
        "neutronspersec": Override(userparam=False),
        "preselection": Override(unit="charge_unit"),
    }

    def _prepare_params(self):
        params = [f"{k}={v}" for k, v in self._attached_state.positions.items()]
        
        # Add string parameters from config if present
        if self._attached_config:
            for key in self._attached_config.__dict__:
                if not key.startswith("_"):
                    value = getattr(self._attached_config, key, None)
                    if value is not None and value != "":
                        params.append(f"{key}={value}")
        
        return params

    def _getNeutronsToSimulate(self):
        return int(round(self.preselection * self.rays_per_charge))
