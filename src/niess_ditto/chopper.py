"""Simulated stand-ins for the ESS chopper devices NICOS drives.

A real disc is several NICOS devices: a controller taking start/stop/park commands, a
speed limited to a few values, a delay (ChopDly-S), a park angle, and read-only status.
These mirror the ones a user moves. The mechanical and pulse delays, which no NICOS
device sets on the real instrument, stay plain `SimMotor`s for the admin.
"""
from nicos.core import Attach, Moveable, Override, Param, listof, oneof, status

from .motor import SimMotor


class SimChopperSpeed(SimMotor):
    """A disc speed, limited to the magnitudes the real controller maps.

    Either sign is allowed: the chopper group's convention signs ``Spd_S`` by the
    direction of rotation, and BIFROST's pulse-shaping and frame-overlap discs turn
    NeXus-positive, so they need negative speeds. The real setups don't follow that
    convention yet and map only non-negative ones.
    """

    parameters = {
        "speeds": Param("The speeds the controller accepts, in Hz", type=listof(float),
                        mandatory=True),
    }

    def doIsAllowed(self, target):
        if abs(target) not in {abs(s) for s in self.speeds}:
            return False, f"{target} Hz is not one of ±{sorted(self.speeds)}"
        return True, ""


class SimChopperController(Moveable):
    """A chopper controller: ``start``, ``stop`` or ``park``.

    As the real one does, ``stop`` (and ``park``) first sets the speed to zero, so a
    stopped disc is simulated standing still at its park angle. ``start`` leaves the
    speed where it is: set it again after a stop.
    """

    hardware_access = False
    valuetype = str  # a command in, a state out, as the real controller

    attached_devices = {
        "speed": Attach("The disc's speed", SimChopperSpeed),
    }

    parameters = {
        "state": Param("running, stopped or parked", type=oneof("running", "stopped", "parked"),
                       settable=True, default="running", userparam=False),
    }

    parameter_overrides = {
        "unit": Override(mandatory=False, default=""),
        "fmtstr": Override(default="%s"),
    }

    def doIsAllowed(self, target):
        if target not in ("start", "stop", "park"):
            return False, "use start, stop or park"
        return True, ""

    def doStart(self, target):
        if target in ("stop", "park"):
            self._attached_speed.maw(0)
        self.state = {"start": "running", "stop": "stopped", "park": "parked"}[target]

    def doRead(self, maxage=0):
        return self.state

    def isAtTarget(self, pos=None, target=None):
        # a command in, a state out: there is no position to compare with the target
        return True

    def doStatus(self, maxage=0):
        return status.OK, self.state

    @property
    def running(self):
        return self.state == "running"
