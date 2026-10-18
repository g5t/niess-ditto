# ruff: noqa: F821
description = "system setup"

group = "lowlevel"

sysconfig = dict(
    cache="localhost",
    instrument="BIFROST",
    experiment="Exp",
    datasinks=["conssink", "daemonsink", "liveview"],
)

modules = ["nicos.commands.standard", "nicos_ess.commands"]

devices = dict(
    BIFROST=device(
        "nicos.devices.instrument.Instrument",
        description="instrument model object",
        facility="European Spallation Source (ERIC)",
        instrument="DITTO",
        responsible="gregory.tucker@ess.eu",
        website="https://github.com/g5t/niess-ditto.git",
    ),
    Sample=device(
        "nicos_ess.devices.sample.EssSample",
        description="The currently used sample",
    ),
    Exp=device(
        "nicos_ess.devices.experiment.EssExperiment",
        description="experiment object",
        dataroot="/tmp/nicos-data",
        sample="Sample",
        cache_filepath="/tmp/nicos-data/cached_proposals.json",
    ),
    pnp_listener=device(
        "nicos_ess.devices.pnp_listener.UDPHeartbeatsManager",
        description="Listens for PnP heartbeats",
        port=24601,
    ),
    conssink=device("nicos_ess.devices.datasinks.console_scan_sink.ConsoleScanSink"),
    daemonsink=device("nicos.devices.datasinks.DaemonSink"),
    liveview=device("nicos.devices.datasinks.LiveViewSink"),
)
