"""BIFROST's incident band, set through all six choppers at once.

Not the bandwidth chopper alone: the band a user asks for fixes every disc's speed and
experiment delay (ChopDly-S), pulse shaping and frame overlap included. The settings
come from `chopcal.nicos.bifrost`, keyed by the real instrument's NICOS device names,
and are moved through whichever devices stand for those names here, so the same
calculation serves DITTO and, with real devices behind the names, the instrument.
"""
from nicos import session
from nicos.core import Moveable, Override, Param, dictof, floatrange, listof, status, usermethod
from nicos.core.errors import MoveError


class IncidentBand(Moveable):
    """The incident band: move to the lowest incident energy to pass, in meV.

    ``set_wavelength_max(z)`` sets the band by its longest wavelength instead, in
    angstrom, which chopcal treats as overriding the energy. ``shaping_time`` is the
    pulse-shaping opening, in seconds.
    """

    hardware_access = False
    valuetype = floatrange(0)

    parameters = {
        "devices": Param("chopcal's NICOS name for each setting -> the device to move",
                         type=dictof(str, str), mandatory=True),
        "controllers": Param("The chopper controllers, all of which must be running",
                             type=listof(str), default=[]),
        "pulse_delay_device": Param("The device holding BeamPosDly-S, in ns",
                                    type=str, mandatory=True),
        "shaping_time": Param("Pulse-shaping opening time", type=floatrange(1e-6),
                              settable=True, default=2e-4, unit="s"),
        "wavelength_max": Param("Longest wavelength to pass, if set by it (else 0)",
                                type=floatrange(0), settable=True, default=0.0,
                                unit="angstrom"),
    }

    parameter_overrides = {
        "unit": Override(mandatory=False, default="meV"),
    }

    def doIsAllowed(self, target):
        stopped = [name for name in self.controllers
                   if not session.getDevice(name).running]
        if stopped:
            return False, f"start {', '.join(stopped)} first"
        return True, ""

    def settings(self, energy_min=None, wavelength_max=None):
        """{device name: value} for a band, without moving anything."""
        from chopcal.nicos import bifrost

        speeds = session.getDevice(self.devices["psc1_chopper_speed"]).speeds
        values = bifrost(session.getDevice(self.pulse_delay_device).read(0),
                         energy_min=energy_min, wavelength_max=wavelength_max or None,
                         shaping_time=self.shaping_time,
                         pulse_shaping_speed_max=max(abs(s) for s in speeds))
        return {self.devices[key]: value for key, value in values.items()}

    def doStart(self, target):
        self.wavelength_max = 0.0
        self._move(self.settings(energy_min=target))

    @usermethod
    def set_wavelength_max(self, wavelength):
        """Set the band by the longest wavelength it passes, in angstrom."""
        allowed, why = self.doIsAllowed(0)
        if not allowed:
            raise MoveError(self, why)
        self._move(self.settings(wavelength_max=wavelength))
        self.wavelength_max = wavelength

    def _move(self, values):
        for name, value in values.items():
            session.getDevice(name).maw(value)

    def doRead(self, maxage=0):
        return self.target if not self.wavelength_max and self.target is not None else 0.0

    def doStatus(self, maxage=0):
        return status.OK, ""

    def simulation_parameters(self, target):
        """The McStas parameters a move to ``target`` would set, for planning a scan."""
        out = {}
        for name, value in self.settings(energy_min=target).items():
            out.update(session.getDevice(name).simulation_parameters(value))
        return out
