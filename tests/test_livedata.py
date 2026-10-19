from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from nicos.core import status

from niess_ditto import livedata
from niess_ditto.livedata import SimLiveDataCollector
from niess_ditto.setup_generator import LIVEDATA, livedata_devices


def test_the_real_collector_counts_on_charge_with_its_channels():
    import nicos_ess
    from niess_ditto.translator import read_setups
    real = read_setups([Path(nicos_ess.__file__).parent / "bifrost" / "setups"])
    devices = livedata_devices(real, "broker:9092", 3600.0)

    cls, config = devices["livedata_collector"]
    assert cls == "niess_ditto.livedata.SimLiveDataCollector"
    assert config["brokers"] == ["broker:9092"] and config["monitors"] == ["charge"]
    assert config["data_topics"] == ["bifrost_livedata_nicos_data"]
    for channel in config["others"]:
        assert devices[channel][0] == f"{LIVEDATA}.DataChannel"
        assert devices[channel][1]["data_timeout"] == 3600.0
    assert "psc_monitor" in config["others"] and "timer" in devices


def _channel(name, last_update=None):
    return NS(name=name, _last_update=last_update)


def _da00(when):
    return NS(data=[NS(name="time", data=np.array([when]))])


@pytest.fixture
def collector(monkeypatch):
    """The waiting logic alone: the base collector reports the charge preset reached."""
    monkeypatch.setattr(livedata.LiveDataCollector, "doStatus",
                        lambda self, maxage=0: (status.OK, ""))
    clock = NS(now=100.0)
    monkeypatch.setattr(livedata.time, "monotonic", lambda: clock.now)
    det = NS(_data_channels=[_channel("monitor"), _channel("image")], _counting=True,
             _point_done=None, _moved={}, settle=3.0, catchup_timeout=120.0, clock=clock)
    return det


def _status(det):
    return SimLiveDataCollector.doStatus(det)


def _arrive(det, monkeypatch, name, when):
    def accept(self, timestamp_ns, da):
        for ch in self._data_channels:
            if ch.name == name:
                ch._last_update = det.clock.now
    monkeypatch.setattr(livedata.LiveDataCollector, "_dispatch_to_channels", accept)
    SimLiveDataCollector._dispatch_to_channels(det, 0, _da00(when))


def test_the_count_waits_for_every_channel_then_for_them_to_settle(collector, monkeypatch):
    assert _status(collector)[0] == status.BUSY  # point done, nothing reduced yet
    _arrive(collector, monkeypatch, "image", 1)
    assert _status(collector)[0] == status.BUSY  # the monitor histogram is still due
    collector.clock.now = 101.0
    _arrive(collector, monkeypatch, "monitor", 1)
    collector.clock.now = 103.5
    _arrive(collector, monkeypatch, "image", 2)  # the event backlog still being reduced
    collector.clock.now = 106.0
    assert _status(collector)[0] == status.BUSY
    collector.clock.now = 106.6
    assert _status(collector)[0] == status.OK


def test_a_republished_output_is_not_progress(collector, monkeypatch):
    _status(collector)
    _arrive(collector, monkeypatch, "image", 1)
    _arrive(collector, monkeypatch, "monitor", 1)
    collector.clock.now = 102.0
    _arrive(collector, monkeypatch, "image", 1)  # same `time`: nothing new reduced
    collector.clock.now = 103.0
    assert _status(collector)[0] == status.OK


def test_the_count_gives_up_waiting_and_leaves_the_channels_to_fail(collector, monkeypatch):
    _status(collector)
    collector.clock.now = 220.0
    assert _status(collector)[0] == status.OK


def test_outside_a_count_the_status_is_the_collectors(collector):
    collector._counting = False
    assert _status(collector) == (status.OK, "")
