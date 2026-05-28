from nicos.core import Attach, HasLimits, Moveable, Override, Param, status

from .state import SimState


class SimMotor(HasLimits, Moveable):
    """Instantaneous moveable backed by SimState and an EPICS mailbox PV."""

    hardware_access = False

    attached_devices = {
        "state": Attach("Shared simulation state", SimState),
    }

    parameters = {
        "pv_prefix": Param(
            "EPICS PV prefix used by the mailbox",
            type=str,
            default="mcstas:",
        ),
    }

    parameter_overrides = {
        "unit": Override(mandatory=False, default=""),
    }

    def doStart(self, target):
        self._attached_state.set_motor(self.name, target)
        self._put_epics(target)

    def doRead(self, maxage=0):
        return self._attached_state.get_motor(self.name)

    def doStatus(self, maxage=0):
        return status.OK, "idle"

    def _put_epics(self, value):
        try:
            from p4p.client.thread import Context

            ctx = Context("pva")
            try:
                ctx.put(f"{self.pv_prefix}{self.name}", value)
            finally:
                ctx.disconnect()
        except (ImportError, OSError, RuntimeError, ValueError) as err:
            self.log.warning("EPICS put failed for %s: %s", self.name, err)
