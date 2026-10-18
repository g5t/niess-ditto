from nicos.core import Attach, HasLimits, Moveable, Override, Param, status

from .state import SimState


class SimMotor(HasLimits, Moveable):
    """An instantaneous moveable that sets one McStas parameter.

    Nothing is written to EPICS here: before each simulated point `SimDetector` puts
    every parameter onto the PVs the NeXus file records, using mccode-plumber's own
    publisher, so the file holds what was simulated.
    """

    hardware_access = False

    attached_devices = {
        "state": Attach("Shared simulation state", SimState),
    }

    parameters = {
        "parameter": Param(
            "The McStas parameter this device sets",
            type=str,
            mandatory=True,
        ),
    }

    parameter_overrides = {
        "unit": Override(mandatory=False, default=""),
    }

    def doStart(self, target):
        self._attached_state.set_motor(self.parameter, target)

    def doRead(self, maxage=0):
        return self._attached_state.get_motor(self.parameter, self.target or 0)

    def doStatus(self, maxage=0):
        return status.OK, "idle"

    def simulation_parameters(self, target):
        """The parameter values moving to ``target`` would simulate."""
        return {self.parameter: target}
