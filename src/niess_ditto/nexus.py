"""ESS' file-writing devices, adjusted for a file-writer that DITTO runs itself."""
from pathlib import Path

from nicos.core import Override, Param, nonemptystring
from nicos_ess.devices.datasinks.file_writer import FileWriterControlSink
from nicos_ess.devices.datasinks.nexus_structure import NexusStructureJsonFile


class NexusStructureFile(NexusStructureJsonFile):
    """ESS' structure provider, reading a structure from anywhere.

    The ESS device only takes paths inside NICOS' working directory; DITTO's structure
    is written next to the simulation's other files.
    """

    parameter_overrides = {
        "nexus_config_path": Override(type=str),
    }


class LocalFileWriterControlSink(FileWriterControlSink):
    """ESS' file-writer control, creating the proposal directory the file goes in.

    The job names a file under the proposal's directory, relative to the file-writer's
    working directory. At ESS that directory exists on the writer's storage already;
    kafka-to-nexus does not create it, so here it is made before the job is sent.
    """

    parameters = {
        "writer_work_dir": Param("The working directory of the kafka-to-nexus DITTO runs",
                                 type=nonemptystring, mandatory=True),
    }

    def _generate_filepath(self, file_num):
        filepath = FileWriterControlSink._generate_filepath(self, file_num)
        (Path(self.writer_work_dir) / filepath).parent.mkdir(parents=True, exist_ok=True)
        return filepath
