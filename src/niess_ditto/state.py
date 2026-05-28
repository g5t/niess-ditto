from nicos.core import Device, Param, anytype, dictof


class SimState(Device):
    """Shared in-process state store for a DITTO simulation."""

    hardware_access = False

    parameters = {
        "positions": Param(
            "Current motor positions keyed by device name",
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
