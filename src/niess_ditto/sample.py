"""A sample a user describes once, for the simulation and for the NeXus file.

A sample script is a Python file defining two names::

    sample = Vanadium(...)            # a niess section, put on the sample table
    nexus = {                         # the file's NXsample group
        "name": "vanadium rod",
        "chemical_formula": "V",
        "unit_cell_abc": ([3.03, 3.03, 3.03], "angstrom"),
    }

Each ``nexus`` value is a value, a ``(value, units)`` pair, or a file-writer JSON node
used as it is. ``load_sample("vanadium.py")`` builds the instrument around ``sample`` with
the setup's ``builder``, which the counts then simulate, and every file started after it
has ``nexus`` as ``/entry/sample``, where NICOS adds its own sample information too.

The devices were made for the setup's instrument, so a sample may not need a parameter
that instrument lacks, unless it has a default. Its primary spectrometer is unchanged, so
restage's cached primaries still serve it.
"""
import runpy
from datetime import datetime
from importlib import import_module
from pathlib import Path

from nicos.core import MASTER, Override, Param, Readable, anytype, nonemptystring, usermethod


def nxsample(values: dict) -> dict:
    """The NXsample group of a sample script's ``nexus``."""
    from nicos_ess.utilities.json_utils import generate_dataset_json, generate_group_json

    children = []
    for name, value in values.items():
        if isinstance(value, dict):
            children.append(value)
            continue
        value, units = value if isinstance(value, tuple) else (value, None)
        children.append(generate_dataset_json(name, value, units))
    return generate_group_json("sample", "NXsample", children)


def builder_function(spec: str):
    """``"path/to/file.py:function"`` or ``"module:function"``."""
    where, _, name = spec.rpartition(":")
    if not where or not name:
        raise ValueError(f"builder {spec!r} is not 'file.py:function' or 'module:function'")
    if where.endswith(".py"):
        return runpy.run_path(where, run_name="niess_ditto_builder")[name]
    return getattr(import_module(where), name)


def unsettable_parameters(instr, base) -> list[str]:
    """Parameters of ``instr`` that ``base`` lacks and nothing would give a value."""
    have = {p.name for p in base.parameters}
    return sorted(p.name for p in instr.parameters
                  if p.name not in have and not p.value.has_value)


class SimSample(Readable):
    """The simulated sample: ``load_sample(script)``, or ``clear_sample()`` for the
    setup's own."""

    hardware_access = False
    valuetype = str

    parameter_overrides = {
        "unit": Override(mandatory=False, default=""),
    }

    parameters = {
        "builder": Param("Builds the instrument around a niess sample: "
                         "'file.py:function' or 'module:function'",
                         type=nonemptystring, mandatory=True),
        "base_instrument": Param("The setup's instrument, which the devices were made for",
                                 type=nonemptystring, mandatory=True),
        "workdir": Param("Where the instruments built for samples go",
                         type=nonemptystring, default="/tmp/ditto/samples"),
        "script": Param("The loaded sample script, empty for the setup's own sample",
                        type=str, default="", internal=True),
        "instrument": Param("The instrument built for it, empty for the setup's",
                            type=str, default="", internal=True),
        "nexus": Param("Its NXsample group, as file-writer JSON", type=anytype,
                       default={}, internal=True),
    }

    def doInit(self, mode):
        if mode == MASTER and self.instrument and not Path(self.instrument).exists():
            self.log.warning("the instrument built for %s is gone; using the setup's",
                             self.script)
            self.clear_sample()

    def doRead(self, maxage=0):
        return Path(self.script).name if self.script else "setup sample"

    @usermethod
    def load_sample(self, script):
        """Simulate the sample ``script`` defines, and describe it in the next files."""
        from mccode_antlr.io.json import save_json
        from mccode_plumber.mccode import get_mcstas_instr

        script = str(Path(script).resolve())
        defined = runpy.run_path(script, run_name="niess_ditto_sample")
        if "sample" not in defined:
            raise ValueError(f"{script} defines no 'sample'")
        nexus = nxsample(defined.get("nexus") or {"name": Path(script).stem})

        self.log.info("building the instrument around %s", Path(script).name)
        instr = builder_function(self.builder)(defined["sample"])
        missing = unsettable_parameters(instr, get_mcstas_instr(self.base_instrument))
        if missing:
            raise ValueError(f"the sample needs parameters no device sets: {', '.join(missing)}")
        stamp = datetime.now().strftime("%y%m%dT%H%M%S")
        path = Path(self.workdir) / f"{instr.name}_{Path(script).stem}_{stamp}.instr.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json(instr, path)

        self._setROParam("script", script)
        self._setROParam("nexus", nexus)
        self._setROParam("instrument", str(path))
        self.read(0)

    @usermethod
    def clear_sample(self):
        """Go back to the setup's own sample."""
        for name, value in (("script", ""), ("nexus", {}), ("instrument", "")):
            self._setROParam(name, value)
        self.read(0)
