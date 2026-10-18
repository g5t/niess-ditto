"""ESS' file-writing devices, adjusted for a file-writer that DITTO runs itself."""
from pathlib import Path

from copy import deepcopy

from nicos.core import Attach, Override, Param, nonemptystring
from nicos_ess.devices.datasinks.file_writer import FileWriterControlSink
from nicos_ess.devices.datasinks.nexus_structure import NexusStructureJsonFile

from .sample import SimSample, put_sample


class NexusStructureFile(NexusStructureJsonFile):
    """ESS' structure provider, reading a structure from anywhere.

    The ESS device only takes paths inside NICOS' working directory; DITTO's structure
    is written next to the simulation's other files. A loaded sample script's NXsample
    group goes in as ``/entry/sample``, before NICOS adds its own sample information;
    without one, the structure's own or an empty group does. Either links its depends_on
    to that of the instrument's ``sample_frame``, for the sample's orientation.
    """

    attached_devices = {
        "sample": Attach("The sample, when it can be changed", SimSample, optional=True),
    }

    parameters = {
        "sample_frame": Param("The instrument's group at the sample, whose depends_on "
                              "the NXsample group links to", type=str,
                              default="/entry/instrument/sample"),
    }

    parameter_overrides = {
        "nexus_config_path": Override(type=str),
    }

    def _load_structure(self):
        structure = NexusStructureJsonFile._load_structure(self)
        sample = self._attached_sample
        loaded = deepcopy(sample.nexus) if sample is not None and sample.nexus else None
        frame = self.sample_frame
        try:
            self._get_node(structure, frame)
        except KeyError:
            self.log.warning("no %s in the structure: the sample has no depends_on", frame)
            frame = None
        put_sample(self._get_node(structure, "/entry"), loaded, frame)
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
