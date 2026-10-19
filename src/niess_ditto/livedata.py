"""Counting a DITTO digital model through esslivedata, as the real instrument counts.

The real BIFROST counts with ESS' `LiveDataCollector`: esslivedata reduces the event and
monitor streams, and NICOS' channels show what it publishes. `SimLiveDataCollector` does
the same with one difference: the count is a simulation point, preset in proton charge
by `niess_ditto.detector.ChargeChannel`, rather than a time.

When the point finishes, its events have been sent and its monitor histograms published,
but esslivedata may still be reducing them. The count therefore ends only once every
channel has received data from this count and none has moved on for `settle` seconds.
"""
import time

import numpy as np
from nicos.core import Param, floatrange, status
from nicos.devices.generic.detector import Detector
from nicos_ess.devices.datasources.livedata import LiveDataCollector


def _time_of(da00):
    """The instant an esslivedata output refers to: its job's latest observation."""
    for variable in da00.data:
        if getattr(variable, "name", None) == "time":
            return np.asarray(variable.data).tobytes()
    return None


class SimLiveDataCollector(LiveDataCollector):
    """ESS' livedata collector, counting a simulation point on charge."""

    parameters = {
        "settle": Param("Seconds every channel's data must stand still after the "
                        "simulation before the count ends",
                        type=floatrange(0), default=3.0, settable=True, unit="s"),
        "catchup_timeout": Param("Longest wait for esslivedata after the simulation",
                                 type=floatrange(0), default=120.0, settable=True,
                                 unit="s"),
    }

    _counting = False
    _point_done = None  # monotonic time the simulation point finished
    _moved = None  # channel name -> (its latest `time`, monotonic time it changed)

    def doStart(self):
        """Reset esslivedata's accumulation and start the simulation point.

        `LiveDataCollector` first waits, per channel, for the accumulation it is about
        to reset: a real instrument always has one. A digital model has data only
        while it counts, so a channel that has never received any is armed as it is,
        and takes the first data it sees.
        """
        for ch in self._data_channels:
            if ch._has_baseline.is_set():
                ch.arm_reset()
            else:
                ch._gate_generation = None
                ch._last_update = None
        for workflow_id in self._workflow_ids():
            self.send_workflow_reset_command(workflow_id)
        self._moved = {}
        self._point_done = None
        self._counting = True
        Detector.doStart(self)

    def doFinish(self):
        self._counting = False
        LiveDataCollector.doFinish(self)

    def doStop(self):
        self._counting = False
        LiveDataCollector.doStop(self)

    def _dispatch_to_channels(self, timestamp_ns, da):
        before = {ch.name: ch._last_update for ch in self._data_channels}
        LiveDataCollector._dispatch_to_channels(self, timestamp_ns, da)
        if self._moved is None:
            return
        stamp = _time_of(da)
        now = time.monotonic()
        for ch in self._data_channels:
            accepted = ch._last_update != before[ch.name]
            if accepted and self._moved.get(ch.name, (None,))[0] != stamp:
                self._moved[ch.name] = (stamp, now)

    def doStatus(self, maxage=0):
        st, text = LiveDataCollector.doStatus(self, maxage)
        if not self._counting or st != status.OK:
            return st, text
        # The charge preset is reached: the simulation point is done
        now = time.monotonic()
        if self._point_done is None:
            self._point_done = now
        if now - self._point_done >= self.catchup_timeout:
            # Channels still without data fail the count in their doFinish
            return st, text
        moved = [self._moved.get(ch.name, (None, None))[1] for ch in self._data_channels]
        if None in moved:
            return status.BUSY, "waiting for esslivedata"
        if now - max(moved + [self._point_done]) < self.settle:
            return status.BUSY, "waiting for esslivedata to settle"
        return st, text
