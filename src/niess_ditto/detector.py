"""Counting with a DITTO digital model: each count is one restage point.

`SimDetector` takes the place of NICOS' `McStasSimulation` binary runner. A count hands
the current parameter values to ``restage.splitrun``, which simulates the primary
spectrometer only when no cached one matches, and the secondary every time, streaming
its events to the EFU. Before the point, mccode-plumber's own publisher puts every value
onto the PVs the NeXus file records, the chopper ones `mp-tdc` serves included; after
it, the monitors are sent to Kafka. That is what ``mp-nexus-splitrun`` does for a scan,
one count at a time.

Where the instrument is split is chosen once per scan, from all of its planned points,
with restage's own rule: scanning the sample rotation shares one primary between every
point, scanning a slit before the sample splits earlier so that it still can.
"""
from datetime import datetime
from itertools import count as counter
from pathlib import Path

from nicos import session
from nicos.core import (
    Attach, MASTER, Override, Param, Value, Waitable, dictof, floatrange, intrange,
    nonemptystring,
)
from nicos.devices.generic.detector import ActiveChannel
from nicos.devices.mcstas import McStasSimulation

from .sample import SimSample
from .state import SimState


class SimDetector(McStasSimulation):
    """Runs one restage point per count, from the values in `SimState`."""

    attached_devices = {
        "state": Attach("Shared simulation state", SimState),
        "sample": Attach("The sample, when it can be changed", SimSample, optional=True),
    }

    parameters = {
        "instrument": Param("The mccode-antlr JSON instrument (the live build)",
                            type=nonemptystring, mandatory=True),
        "structure": Param("The NeXus structure the file-writer fills",
                           type=nonemptystring, mandatory=True),
        "broker": Param("Kafka broker", type=str, default="localhost:9092"),
        "split_candidates": Param("Components restage may split the instrument at",
                                  type=str, default="split_at,split_before_sample"),
        "rays_per_charge": Param("Primary rays simulated per unit of the charge preset",
                                 type=floatrange(1e-10), settable=True, default=1.0),
        "minimum_particles": Param("restage's minimum primary MCPL particle count (0: none)",
                                   type=intrange(0, 2**53), settable=True, default=0),
        "maximum_particles": Param("restage's maximum primary MCPL particle count (0: none)",
                                   type=intrange(0, 2**53), settable=True, default=0),
        "mcpl_input_component": Param("The MCPL input the secondary reads",
                                      type=str, default="MCPL_input_once"),
        "mcpl_output_parameters": Param("Parameters for the primary's MCPL output",
                                        type=dictof(str, str), default={"weight_mode": "1"}),
        "parallel": Param("Run the simulations with MPI", type=bool, settable=True,
                          default=True),
        "process_count": Param("MPI process count (0: MPI's default)",
                               type=intrange(0, 4096), default=0),
        "workdir": Param("Where each count's restage output goes",
                         type=nonemptystring, default="/tmp/ditto/counts"),
        "fixed": Param("Parameters set on every count but by no device, e.g. strings",
                       type=dictof(str, str), default={}),
    }

    parameter_overrides = {
        "mcstasprog": Override(mandatory=False, default=""),
        "neutronspersec": Override(userparam=False),
        "preselection": Override(unit="charge"),
    }

    _plan = None  # (scan, split) for the scan being counted in
    _instr = None
    _instr_path = None

    def doInit(self, mode):
        McStasSimulation.doInit(self, mode)
        self._runs = counter()

    def _instrument(self):
        sample = self._attached_sample
        return (sample.instrument if sample is not None else "") or self.instrument

    def _load(self):
        """Read the instrument and structure, on the first count and after the sample
        changes: only the process that counts needs them."""
        path = self._instrument()
        if path == self._instr_path:
            return
        from mccode_plumber.manage.orchestrate import (
            RUN_PV, PREFIX, get_chopper_specs, get_simulated_logs, load_file_json,
            monitor_sources_and_topics,
        )
        from mccode_plumber.mccode import get_mcstas_instr
        from mccode_plumber.splitrun import (
            monitors_to_kafka_callback_for_topics, parameter_pvs_callback_with_arguments,
        )
        self._instr = get_mcstas_instr(path)
        self._instr_path = path
        self._plan = None
        structure = load_file_json(self.structure)
        choppers = [c for c, _ in get_chopper_specs(structure)]
        logs = get_simulated_logs(structure, choppers)
        self._pre = parameter_pvs_callback_with_arguments(
            self._instr, choppers, RUN_PV, logs=logs, prefix=PREFIX)
        sources, _ = monitor_sources_and_topics(structure, self._instr)
        self._post = monitors_to_kafka_callback_for_topics(broker=self.broker, sources=sources)

    # -- what to simulate ---------------------------------------------------------------

    def _values(self):
        """The values of the instrument's parameters: a sample may not use them all."""
        self._load()
        names = {p.name for p in self._instr.parameters}
        values = {**self.fixed, **self._attached_state.positions}
        return {k: v for k, v in values.items() if k in names}

    def _planned_points(self, values):
        """Every point of the running scan, as parameter values, or None outside one.

        NICOS keeps the running scan as ``session._currentscan`` (since 2014), and it
        knows its devices and every start position before the first point is counted.
        A device that cannot say which parameters it sets leaves them unchanged.
        """
        scan = getattr(session, "_currentscan", None)
        if scan is None:
            return scan, None
        points = []
        for positions in scan._startpositions:
            point = dict(values)
            for device, position in zip(scan._devices, positions):
                planner = getattr(device, "simulation_parameters", None)
                if planner is not None:
                    point.update(planner(position))
            points.append(point)
        return scan, points

    def _split(self, values):
        """The split for this count: chosen once per scan from all its points."""
        from restage.split_points import choose_split

        self._load()
        scan, points = self._planned_points(values)
        if scan is not None and self._plan and self._plan[0] is scan:
            return self._plan[1]
        candidates = [c.strip() for c in self.split_candidates.split(",") if c.strip()]
        # A lone count, or a scan whose points share nothing: the latest split, so that
        # a later count can reuse its primary from restage's cache.
        chosen = choose_split(self._instr, self.split_candidates, points or [values])
        chosen = chosen or candidates[-1]
        self._plan = (scan, chosen)
        self.log.info("splitting %s at %s", self._instr.name, chosen)
        return chosen

    # -- the McStasSimulation hooks ----------------------------------------------------

    def _prepare_params(self):
        return [f"{k}={v}" for k, v in self._values().items()]

    def _prepare(self, *datafiles):
        if not self._mcstas_params:
            self._mcstas_params = self._prepare_params()
            self._start_time = None

    def _getNeutronsToSimulate(self):
        return int(round(self.preselection * self.rays_per_charge))

    def _run(self):
        from time import monotonic
        from mccode_antlr.run.range import parse_scan_parameters
        from restage.splitrun import splitrun

        try:
            self._load()
            values = self._values()
            # unique across sessions: restage refuses an output directory that exists
            stamp = datetime.now().strftime("%y%m%dT%H%M%S")
            out_dir = Path(self.workdir) / f"{self._instr.name}_{stamp}_{next(self._runs):03d}"
            out_dir.parent.mkdir(parents=True, exist_ok=True)
            split = self._split(values)
            self._start_time = monotonic()
            pre, pre_args = self._pre
            post, post_args = self._post
            splitrun(
                self._instr, parse_scan_parameters(self._mcstas_params), {},
                split_at=split,
                ncount=self._getNeutronsToSimulate(),
                out_dir=str(out_dir),
                minimum_particle_count=self.minimum_particles or None,
                maximum_particle_count=self.maximum_particles or None,
                parallel=self.parallel, process_count=self.process_count,
                mcpl_input_component=self.mcpl_input_component or None,
                mcpl_output_parameters=dict(self.mcpl_output_parameters) or None,
                callback=post, callback_arguments=post_args,
                pre_callback=pre, pre_callback_arguments=pre_args,
            )
        except Exception:
            self.log.exception("simulation failed")
        finally:
            self._started = False


class ChargeChannel(ActiveChannel, Waitable):
    """The count preset, as proton charge: ``count(charge=...)``.

    The preset's name is this device's name. `SimDetector.rays_per_charge` turns it into
    the number of primary rays to simulate.
    """

    attached_devices = {
        "mcstas": Attach("The simulation", SimDetector),
    }

    parameters = {
        "curvalue": Param("Current value", settable=True, unit="main"),
    }

    parameter_overrides = {
        "unit": Override(default="uC"),
    }

    def doInit(self, mode):
        if mode == MASTER:
            self.curvalue = 0

    def setChannelPreset(self, name, value):
        ActiveChannel.setChannelPreset(self, name, value)
        self._attached_mcstas.preselection = value

    def doPrepare(self):
        self._attached_mcstas._prepare()

    def doStart(self):
        self._attached_mcstas._start()

    def doStatus(self, maxage=0):
        return Waitable.doStatus(self, maxage)

    def doRead(self, maxage=0):
        done = not self._attached_mcstas._started
        self.curvalue = self._attached_mcstas.preselection if done else 0
        return self.curvalue

    def doFinish(self):
        self._attached_mcstas._finish()

    def doStop(self):
        self.doFinish()

    def valueInfo(self):
        return (Value(self.name, unit=self.unit, type="monitor", fmtstr="%.3f"),)
