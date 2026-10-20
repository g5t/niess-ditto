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

With ``replay`` the instrument is the collecting build instead: the point's detector and
monitor rays are written to a collector file, and once it is simulated the count replays
it to the EFUs -- the beam monitor EFU included, so the monitors arrive as events and as
that EFU's histograms, as at the real instrument, not as McStas' histograms. The
parameter values are already on their PVs by then, so the replay sets none of them.
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
        "instrument": Param("The mccode-antlr JSON instrument (the live build, or the "
                            "collecting one with replay)",
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
        # restage repeats the primary until the split has as many rays as the count asks
        # for, each pass at most this many. At its own default, the count itself, a ~1e-3
        # transmission makes that ~1000 short passes: ~5 min at charge=1e5 for what two
        # passes do in ~40 s.
        "maximum_particles": Param("Most rays one pass of the primary simulates "
                                   "(0: restage's default, the count)",
                                   type=intrange(0, 2**53), settable=True, default=10**9),
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
        "replay": Param("Replay each count's collected rays to the EFUs, rather than "
                        "stream detector events live (needs the collecting build)",
                        type=bool, default=False),
        "efu_senders": Param("readout-replay's senders: the EFU for each detector type",
                             type=str, default=""),
        "pulses_per_point": Param("Source pulses each count's events are spread over; "
                                  "the beam monitor EFU sums 14 into each histogram",
                                  type=intrange(0, 10**6), settable=True, default=14),
        "charge_rate": Param("Proton charge per second of beam, to turn the charge preset "
                             "into a counting time (71.43 uC a pulse at 14 Hz)",
                             type=floatrange(1e-10), settable=True, default=1000.0,
                             unit="uC/s"),
        "settle": Param("Seconds to wait after a replay for the EFUs' last events",
                        type=floatrange(0), settable=True, default=2.0, unit="s"),
        "replay_seed": Param("Seed for the replay's sampling (0: non-deterministic)",
                             type=intrange(0, 2**31 - 1), default=0),
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
            # collected monitors reach Kafka through the beam monitor EFU, not as histograms
            post, post_args = (None, None) if self.replay else self._post
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
            if self.replay:
                self._replay(out_dir)
        except Exception:
            self.log.exception("simulation failed")
        finally:
            self._started = False


    def _counting_time(self):
        """The charge preset as the seconds of beam it takes, which the replay draws
        Poisson(weight x seconds) events for."""
        return self.preselection / self.charge_rate

    def _replay(self, out_dir):
        """Send the point's collector files to the EFUs, paced over the count's pulses."""
        import mcstas_readout as ro
        from mccode_plumber.manage.replay import PointPublisher, replay_file

        files = sorted(Path(out_dir).glob("*.h5"))
        if not files:
            self.log.warning("no collector file in %s: is the instrument the collecting "
                             "build?", out_dir)
            return
        paced = {"pulses_per_point": self.pulses_per_point} if self.pulses_per_point else {}
        config = ro.ReplayConfig(
            counting_time=self._counting_time(), seed=self.replay_seed,
            senders_json=Path(self.efu_senders).read_text() if self.efu_senders else None,
            fold_tof=True, **paced)
        # the values went to their PVs before the point was simulated
        publisher = PointPublisher(lambda pars: None)
        for path in files:
            self.log.info("replaying %s", path)
            replay_file(str(path), config, publisher, settle=self.settle)


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
