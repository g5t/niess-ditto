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
speed device, which does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PREFIX = 'mcstas:'
_FIELD = re.compile(r'\.[A-Z]+$')
_PV_KEYS = ('motorpv', 'readpv', 'writepv')


def record(pv: str) -> str:
    """The EPICS record a PV names: no simulation prefix, no record field."""
    return _FIELD.sub('', pv.removeprefix(PREFIX))


@dataclass
class Translation:
    #: NICOS device name -> the McStas parameter it sets
    parameters: dict[str, str] = field(default_factory=dict)
    #: NICOS device name -> (class name, configuration) from the real setup
    devices: dict[str, tuple[str, dict]] = field(default_factory=dict)
    #: chopper controller name -> the name of the speed device it attaches
    controllers: dict[str, str] = field(default_factory=dict)

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
        pvs = {record(config[key]) for key in _PV_KEYS if isinstance(config.get(key), str)}
        found = {by_record[pv] for pv in pvs if pv in by_record}
        if len(found) > 1:
            raise ValueError(f'NICOS device {name} addresses PVs of {sorted(found)}')
        if found:
            out.parameters[name] = found.pop()
            out.devices[name] = (classname, config)
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
