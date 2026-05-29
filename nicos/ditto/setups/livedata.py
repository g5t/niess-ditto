description = "The livedata."

devices = dict(
    detector_sliding=device(
        "nicos_ess.devices.datasources.livedata.DataChannel",
        description="A ditto livedata channel",
        type="counter",
    ),
    detector_cumulative=device(
        "nicos_ess.devices.datasources.livedata.DataChannel",
        description="A ditto livedata channel",
        type="counter",
    ),
    detector_roi=device(
        "nicos_ess.devices.datasources.livedata.DataChannel",
        description="A ditto livedata channel",
        type="counter",
    ),
    livedata_collector=device(
        "nicos_ess.devices.datasources.livedata.LiveDataCollector",
        description="The ditto livedata collector",
        brokers=["localhost:9092"],
        data_topics=["ditto_livedata_data"],
        commands_topic="ditto_livedata_commands",
        others=["detector_sliding", "detector_cumulative", "detector_roi"],
    ),
)
