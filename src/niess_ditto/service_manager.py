from pathlib import Path

from nicos.core import Device, MASTER, Param, listof, nonemptystring, usermethod


class SimServiceManager(Device):
    """Runs the data-collection services for the whole time the setup is loaded.

    The services are mccode-plumber's, started as ``mp-nexus-services`` starts them, so
    DITTO gets the same EFU, forwarder, EPICS mailbox (with the PVs the structure names),
    top-dead-centre publisher and file-writer as a plumber run. The forwarder is told
    once, here, which PVs to forward; a plumber run does that per file instead.
    """

    hardware_access = False

    parameters = {
        "instrument": Param("The mccode-antlr JSON instrument (the live build)",
                            type=nonemptystring, mandatory=True),
        "structure": Param("The NeXus structure the file-writer fills",
                           type=nonemptystring, mandatory=True),
        "broker": Param("Kafka broker", type=str, default="localhost:9092"),
        "efu": Param("EFU configurations, as mp-nexus-services --efu takes them "
                     "(empty: plumber's guess from the instrument name)",
                     type=listof(str), default=[]),
        "writer_work_dir": Param("kafka-to-nexus' working directory", type=str, default=""),
    }

    _services = ()
    _forwarded = None

    def doInit(self, mode):
        if mode == MASTER:
            self.start()

    @usermethod
    def start(self):
        """Start the services, unless they are running already."""
        if self._services:
            return
        from mccode_plumber.forwarder import configure_forwarder, forwarder_partial_streams
        from mccode_plumber.manage.orchestrate import (
            PREFIX, TOPICS, chopper_forwarder_streams, efu_parameter, services_kwargs,
            simulated_log_forwarder_streams, start_services, wait_for_services,
        )
        if self.writer_work_dir:
            Path(self.writer_work_dir).mkdir(parents=True, exist_ok=True)
        kwargs = services_kwargs(
            self.instrument, self.structure, self.broker,
            efu=[efu_parameter(e) for e in self.efu] or None,
            writer_working_dir=self.writer_work_dir or None,
        )
        if self.writer_work_dir:
            _ensure_template(Path(self.writer_work_dir), kwargs["instr_name"])
        seen = _status_count(self.broker, TOPICS["status"])
        self._services = start_services(**kwargs)
        wait_for_services(self._services)
        # The forwarder runs with --skip-retrieval: a configuration sent before it is
        # listening is lost. Its first status message says it is.
        _wait_for_status(self.broker, TOPICS["status"], seen)
        streams = forwarder_partial_streams(PREFIX, TOPICS["parameter"], kwargs["instr_parameters"])
        streams += chopper_forwarder_streams(kwargs["choppers"], kwargs["pulse"])
        streams += simulated_log_forwarder_streams(kwargs["simulated_logs"])
        self._forwarded = (streams, f"{self.broker}/{TOPICS['config']}")
        configure_forwarder(streams, self._forwarded[1], PREFIX, TOPICS["parameter"])
        self.log.info("started %d services", len(self._services))

    def doShutdown(self):
        self.stop()

    @usermethod
    def stop(self):
        """Stop the services."""
        from mccode_plumber.forwarder import reset_forwarder
        from mccode_plumber.manage.orchestrate import PREFIX, TOPICS

        if self._forwarded:
            reset_forwarder(*self._forwarded, PREFIX, TOPICS["parameter"])
            self._forwarded = None
        # Each one regardless of the others: a service that died already must not
        # leave the rest running after NICOS has gone.
        for service in self._services:
            try:
                service.stop()
            except Exception as error:  # noqa: BLE001
                self.log.warning("stopping %s: %s", service.name, error)
        self._services = ()


def _ensure_template(work: Path, instrument: str) -> None:
    """An empty file for kafka-to-nexus to start NICOS' jobs from.

    A start message that names its instrument, as NICOS' does, makes the writer copy
    ``<template prefix>/<instrument>/<instrument>.hdf`` and write into the copy; at ESS
    those templates are provided with the writer. Nothing needs to be in it here. It
    must be in HDF5's latest format, which the writer opens for SWMR writing.
    """
    import h5py

    template = work / instrument / f"{instrument}.hdf"
    if not template.exists():
        template.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(template, "w", libver="latest"):
            pass


def _status_count(broker, topic):
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({"bootstrap.servers": broker, "group.id": "niess-ditto-peek"})
    try:
        return consumer.get_watermark_offsets(TopicPartition(topic, 0), timeout=5)[1]
    finally:
        consumer.close()


def _wait_for_status(broker, topic, seen, timeout=60.0):
    from time import monotonic, sleep

    end = monotonic() + timeout
    while _status_count(broker, topic) <= seen:
        if monotonic() > end:
            raise TimeoutError(f"the forwarder published no status on {topic} in {timeout} s")
        sleep(0.5)
