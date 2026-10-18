from nicos.core import Device, Param, anytype, dictof


class SimState(Device):
    """The McStas parameter values the next count simulates, keyed by parameter name.

    Devices write here under the *parameter's* name, not their own, so a device can be
    called whatever the instrument calls it while the simulation still gets the name it
    declares.
    """

    hardware_access = False

    parameters = {
        "positions": Param(
            "Current McStas parameter values keyed by parameter name",
            type=dictof(str, anytype),
            settable=True,
            default={},
            userparam=False,
        ),
    }

    def set_motor(self, name, value):
        pos = dict(self.positions)
        pos[name] = value
        self.positions = pos

    def get_motor(self, name, default=0.0):
        return self.positions.get(name, default)
