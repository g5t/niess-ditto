"""ESS' file-writing devices, adjusted for a file-writer that DITTO runs itself."""
from pathlib import Path

from copy import deepcopy

from nicos.core import Attach, Override, Param, nonemptystring
from nicos_ess.devices.datasinks.file_writer import FileWriterControlSink
from nicos_ess.devices.datasinks.nexus_structure import NexusStructureJsonFile

from .sample import SimSample


class NexusStructureFile(NexusStructureJsonFile):
    """ESS' structure provider, reading a structure from anywhere.

    The ESS device only takes paths inside NICOS' working directory; DITTO's structure
    is written next to the simulation's other files. A loaded sample script's NXsample
    group goes in as ``/entry/sample``, before NICOS adds its own sample information.
    """

    attached_devices = {
        "sample": Attach("The sample, when it can be changed", SimSample, optional=True),
    }

    parameter_overrides = {
        "nexus_config_path": Override(type=str),
    }

    def _load_structure(self):
        structure = NexusStructureJsonFile._load_structure(self)
        sample = self._attached_sample
        if sample is not None and sample.nexus:
            group = deepcopy(sample.nexus)
            entry = self._get_node(structure, "/entry")
            entry["children"] = [c for c in entry["children"]
                                 if c.get("name") != group["name"]] + [group]
            self._refresh_map(structure)
        return structure


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
