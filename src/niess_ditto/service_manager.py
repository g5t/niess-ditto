from nicos.core import ConfigurationError, Device, MASTER, Param, listof, nonemptystring

from mccode_antlr.common.expression import DataType
from mccode_plumber.manage import EPICSMailbox, EventFormationUnit, Forwarder, KafkaToNexus
from mccode_plumber.manage.manager import Triage
from mccode_plumber.manage.orchestrate import (
    PREFIX,
    TOPICS,
    efu_parameter,
    get_instr_name_and_parameters,
    guess_instr_calibration,
    guess_instr_config,
    guess_instr_efu,
    register_topics,
)
from mccode_plumber.manage.efu import EventFormationUnitConfig
from mccode_plumber.manage.forwarder import forwarder_verbosity
from mccode_plumber.manage.writer import writer_verbosity


class SimServiceManager(Device):
    """Owns EFU, mailbox, forwarder and writer-worker process lifecycle."""

    hardware_access = False

    parameters = {
        "instrument_json": Param(
            "Path to the mccode-antlr JSON instrument file",
            type=nonemptystring,
            mandatory=True,
        ),
        "broker": Param(
            "Kafka broker address",
            type=str,
            default="localhost:9092",
        ),
        "efu_configs": Param(
            "EFU configuration strings, each parsed by mccode_plumber efu_parameter()",
            type=listof(str),
            default=[],
        ),
        "writer_work_dir": Param(
            "Optional kafka-to-nexus output working directory",
            type=str,
            default="",
        ),
        "writer_verbosity": Param(
            "Optional kafka-to-nexus verbosity",
            type=str,
            default="",
        ),
        "forwarder_verbosity": Param(
            "Optional EPICS forwarder verbosity",
            type=str,
            default="",
        ),
        "pv_prefix": Param(
            "EPICS PV prefix used by the mailbox",
            type=str,
            default=PREFIX,
        ),
    }

    _services = ()

    def doInit(self, mode):
        if mode != MASTER:
            return
        _ensure_kafka(self.broker)
        instr_name, instr_parameters = get_instr_name_and_parameters(self.instrument_json)
        register_topics(self.broker, list(TOPICS.values()))
        efu_cfgs = self._resolve_efu_configs(instr_name, instr_parameters)
        self._services = self._start_services(instr_parameters, efu_cfgs)
        self.log.info("Started %d DITTO background service(s)", len(self._services))

    def doShutdown(self):
        for service in self._services:
            service.stop()
        self._services = ()

    def _resolve_efu_configs(self, instr_name, instr_parameters):
        if self.efu_configs:
            return [efu_parameter(cfg) for cfg in self.efu_configs]

        default_port = 9000
        port_params = [p for p in instr_parameters if "port" in p.name.lower()]
        if port_params:
            port_expr = port_params[0].value
            if port_expr.has_value and port_expr.data_type == DataType.int:
                default_port = int(port_expr.value)

        return [
            EventFormationUnitConfig.from_dict(
                {
                    "name": instr_name,
                    "binary": guess_instr_efu(instr_name),
                    "config": guess_instr_config(instr_name),
                    "calibration": guess_instr_calibration(instr_name),
                    "topic": TOPICS["event"],
                    "port": default_port,
                }
            )
        ]

    def _start_services(self, instr_parameters, efu_cfgs):
        from colorama import Fore

        services = tuple(
            EventFormationUnit.start(
                style=Fore.BLUE,
                broker=self.broker,
                triage=Triage(ignore=["graphite", ":2003 failed"]),
                **cfg.to_dict(),
            )
            for cfg in efu_cfgs
        ) + (
            Forwarder.start(
                name="FWD",
                style=Fore.GREEN,
                broker=self.broker,
                config=TOPICS["config"],
                status=TOPICS["status"],
                verbosity=forwarder_verbosity(self.forwarder_verbosity),
            ),
            EPICSMailbox.start(
                name="MBX",
                style=Fore.YELLOW,
                parameters=instr_parameters,
                prefix=self.pv_prefix,
            ),
            KafkaToNexus.start(
                name="K2N",
                style=Fore.RED,
                triage=Triage(ignore=["ignored by this consumer instance"]),
                broker=self.broker,
                command=TOPICS["command"],
                pool=TOPICS["pool"],
                work=(self.writer_work_dir or None),
                verbosity=writer_verbosity(self.writer_verbosity),
            ),
        )
        longest_name = max(len(service.name) for service in services)
        for service in services:
            service.name_padding = longest_name - len(service.name)
        return services


def _ensure_kafka(broker, timeout=5.0):
    from confluent_kafka.admin import AdminClient

    client = AdminClient(
        {
            "bootstrap.servers": broker,
            "socket.timeout.ms": int(timeout * 1000),
        }
    )
    metadata = client.list_topics(timeout=timeout)
    if metadata is None:
        raise ConfigurationError(
            f"Kafka broker not reachable at {broker}. "
            "Start a local broker first (for example via stacktainer)."
        )
