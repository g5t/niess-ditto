"""Which NICOS device sets which McStas parameter, worked out from EPICS PV names.

Nothing here names a device or a parameter. Both sides already say which PV they are
about: the real instrument's NICOS setups give each device's ``motorpv``, ``readpv`` or
``writepv``, and the NeXus structure gives each simulated log its source PV and, in its
``simulation_parameter`` attribute, the McStas parameter that fills it. The simulated
source is the real PV behind a ``mcstas:`` prefix, and a motor is logged by a field of
its record (``.RBV``), so dropping both gives the address NICOS uses::

    mcstas:BIFRO-SpRot:MC-RotZ-01:Mtr.RBV  ->  BIFRO-SpRot:MC-RotZ-01:Mtr
        sample_rotation (structure)            sample_stack_rotation (NICOS)

A chopper controller has no PV of its own that a log records, but each one attaches its
speed device, which does. That device reads ``Spd_R`` and writes ``Spd_S``, which ESS
counts positive clockwise facing away from the source; the file records the NeXus sign,
anticlockwise, from ``SpdNexus-R`` (ECDC's Choppers page). So a speed device matches the
``SpdNexus-R`` log, and sets its parameter negated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PREFIX = 'mcstas:'
_FIELD = re.compile(r'\.[A-Z]+$')
_PV_KEYS = ('motorpv', 'readpv', 'writepv')
#: ESS-signed PV suffix -> the NeXus-signed record a file logs instead, of opposite sign
_NEGATED = {':Spd_R': ':SpdNexus-R', ':Spd_S': ':SpdNexus-R'}


def record(pv: str) -> str:
    """The EPICS record a PV names: no simulation prefix, no record field."""
    return _FIELD.sub('', pv.removeprefix(PREFIX))


def _logged(pv: str) -> tuple[str, bool]:
    """The record a file logs for a NICOS PV, and whether it holds the negated value."""
    pv = record(pv)
    for ess, nexus in _NEGATED.items():
        if pv.endswith(ess):
            return pv.removesuffix(ess) + nexus, True
    return pv, False


@dataclass
class Translation:
    #: NICOS device name -> the McStas parameter it sets
    parameters: dict[str, str] = field(default_factory=dict)
    #: NICOS device name -> (class name, configuration) from the real setup
    devices: dict[str, tuple[str, dict]] = field(default_factory=dict)
    #: chopper controller name -> the name of the speed device it attaches
    controllers: dict[str, str] = field(default_factory=dict)
    #: NICOS devices whose value is the negation of their parameter's
    negated: set[str] = field(default_factory=set)

    def device_of(self, parameter: str) -> str | None:
        return next((d for d, p in self.parameters.items() if p == parameter), None)


def translate(structure: dict, setups: dict[str, tuple[str, dict]]) -> Translation:
    """Match ``setups``' devices to the parameters ``structure`` says fill each PV.

    ``setups`` maps every device of the real instrument's setups to its class name and
    configuration, as NICOS reads them. A device matches when any of its PVs is the
    record of a simulated log; a PV shared by two devices is an error, since which one
    the user meant would be a guess.
    """
    from mccode_plumber.manage.orchestrate import get_simulated_logs

    by_record = {}
    for log in get_simulated_logs(structure):
        by_record.setdefault(record(log.source), log.parameter)

    out = Translation()
    for name, (classname, config) in setups.items():
        pvs = {_logged(config[key]) for key in _PV_KEYS if isinstance(config.get(key), str)}
        found = {(by_record[pv], negated) for pv, negated in pvs if pv in by_record}
        if len({parameter for parameter, _ in found}) > 1:
            raise ValueError(f'NICOS device {name} addresses PVs of {sorted(found)}')
        if len(found) > 1:
            raise ValueError(f'NICOS device {name} addresses {found.pop()[0]} with both signs')
        if found:
            parameter, negated = found.pop()
            out.parameters[name] = parameter
            out.devices[name] = (classname, config)
            if negated:
                out.negated.add(name)
    taken = {}
    for name, parameter in out.parameters.items():
        if parameter in taken:
            raise ValueError(f'{parameter} is set by both {taken[parameter]} and {name}')
        taken[parameter] = name
    for name, (classname, config) in setups.items():
        if config.get('speed') in out.parameters:
            out.controllers[name] = config['speed']
    return out


def read_setups(paths, logger=None) -> dict[str, tuple[str, dict]]:
    """Every device in the NICOS setups on ``paths``, as (class name, configuration)."""
    import logging
    from nicos.core.sessions.setups import readSetups

    info = readSetups(list(paths), logger or logging.getLogger('niess_ditto'))
    devices = {}
    for setup in info.values():
        for name, device in ((setup or {}).get('devices') or {}).items():
            devices[name] = (device[0], dict(device[1]))
    return devices
