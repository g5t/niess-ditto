from nicos.core import Attach, HasLimits, Moveable, Override, Param, oneof, status

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
        "sign": Param(
            "The parameter's value is this times the device's: -1 where the real device "
            "counts the other way from the simulation (a chopper's Spd_S)",
            type=oneof(1, -1),
            default=1,
        ),
    }

    parameter_overrides = {
        "unit": Override(mandatory=False, default=""),
    }

    def doStart(self, target):
        self._attached_state.set_motor(self.parameter, self.sign * target)

    def doRead(self, maxage=0):
        value = self._attached_state.get_motor(self.parameter, None)
        return (self.target or 0) if value is None else self.sign * value

    def doStatus(self, maxage=0):
        return status.OK, "idle"

    def simulation_parameters(self, target):
        """The parameter values moving to ``target`` would simulate."""
        return {self.parameter: self.sign * target}
