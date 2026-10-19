# niess-ditto

[![PyPI - Version](https://img.shields.io/pypi/v/niess-ditto.svg)](https://pypi.org/project/niess-ditto)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/niess-ditto.svg)](https://pypi.org/project/niess-ditto)

-----

## Table of Contents

- [Installation](#installation)
- [What it provides](#what-it-provides)
- [Usage in a NICOS setup](#usage-in-a-nicos-setup)
- [Known limits](#known-limits)
- [License](#license)

## Installation

```console
pip install niess-ditto
```

## What it provides

NICOS devices for a DITTO digital model of BIFROST: the instrument is driven through
NICOS as the real one is, each count simulates it with McStas, and its events, logs and
file go through the real ESS data-collection services.

- `niess_ditto.setup_generator.make_ditto_setup(...)` builds a setup's `devices` from
  the live BIFROST instrument (mccode-antlr JSON), its NeXus structure, and the real
  instrument's NICOS setups.
- `niess_ditto.translator` matches the real NICOS devices to McStas parameters by the
  EPICS PV both name, so nothing is hard-coded: `sample_stack_rotation` sets
  `sample_rotation` because both are about `BIFRO-SpRot:MC-RotZ-01:Mtr`. `names=` renames
  any device.
- `SimMotor` (one per parameter), `SimChopperSpeed` (the real controller's speeds only)
  and `SimChopperController` (`start`/`stop`/`park`) stand in for the real devices.
- `IncidentBand` sets all six discs from one lowest incident energy, or a longest
  wavelength, with `chopcal.nicos.bifrost`; it refuses while any disc is stopped.
- `SimDetector` runs each count as one `restage` point, so primary spectrometer
  simulations are reused from restage's cache, and chooses the split once per scan from
  all of its planned points. mccode-plumber's publisher puts every value on the PVs the
  NeXus file records before each point. `ChargeChannel` makes the preset
  `count(charge=...)`.
- `SimServiceManager` starts mccode-plumber's services (EFU, forwarder, EPICS mailbox,
  top-dead-centre publisher, kafka-to-nexus) and configures the forwarder.
- `LocalFileWriterControlSink` and `NexusStructureFile` adapt ESS' file-writer devices
  to a kafka-to-nexus DITTO runs itself.

## Usage in a NICOS setup

See `nicos/ditto/setups/bifrost.py`:

```python
devices = make_ditto_setup(
    instrument_json="/opt/ditto/bifrost_live.instr.json",
    structure_json="/opt/ditto/bifrost_live.json",
    nicos_setups=[Path(nicos_ess.__file__).parent / "bifrost" / "setups"],
)
```

```python
start_filewriting("a3 scan")
maw(incident_band, 4.5)            # meV; or incident_band.set_wavelength_max(3.0)
scan(sample_stack_rotation, 0, 1, 3, charge=100000)
stop_filewriting()
```

The live build and structure come from `bifrost_phonon.py --live` (bifrost-workflow-2609).
Needs a Kafka broker, and the stacktainer splitrun image's EFU, forwarder,
kafka-to-nexus and template-maker.

As at ESS, the file-writer starts each file from a template: `sim_services` makes it
from the structure's datasets with kafka-to-nexus' `template-maker` (again only when the
structure changes), and NICOS' start message carries the streams and links only, 176 kB
instead of 1.5 MB for BIFROST.

## Changing the sample

A sample script defines a niess section, `sample`, and the file's NXsample group,
`nexus` (see `examples/vanadium.py`):

```python
sim_sample.load_sample("examples/vanadium.py")   # ~7 s: the instrument is rebuilt
scan(sample_stack_rotation, 0, 1, 10, charge=100000)
sim_sample.clear_sample()                        # back to the setup's own sample
```

The setup's `DITTO_BUILDER` (`bifrost_phonon.py:ditto_instrument` in
bifrost-workflow-2609) builds the instrument around it. Files started afterwards have
`nexus` as `/entry/sample`, where NICOS adds the Sample device's information too. A
sample may use fewer of the instrument's parameters, or new ones with defaults; one that
needs a parameter no device sets is refused.

## Counting through esslivedata

The real BIFROST counts with ESS' `LiveDataCollector`, whose channels show what
esslivedata reduces from the event and monitor streams. With `livedata=True`
(`DITTO_LIVEDATA=1` for `nicos/ditto/setups/bifrost.py`) the setup takes that collector
and its channels from the real instrument's setups, and the collector becomes
`niess_ditto.livedata.SimLiveDataCollector`:

```python
SetDetectors(livedata_collector)
count(charge=100000)
```

A count resets esslivedata's accumulation, simulates the point, then waits until every
channel has data from this count and none has changed for `settle` seconds (at most
`catchup_timeout`). Each monitor sends one histogram per point, when the point has been
simulated, so a channel's `data_timeout` is an hour rather than the real ten seconds.

esslivedata must run against the same broker, with `--instrument bifrost`,
`--log-source-prefix mcstas:` so that it matches the simulated PVs, and
`--monitor-sources-by-name` so that it matches the monitors, which the simulation
publishes under their NeXus group names rather than `cbm1`...`cbm5`. Both options are
on our esslivedata branches, not yet upstream.

## Known limits

- The services start in NICOS' master process. A session that only becomes master
  after loading the setup (`nicos-script -M`) calls `sim_services.start()` itself.
- The simulation runs in NICOS' working directory, so data files the sample reads by
  relative name (BIFROST's `.lau` reflection list) must be there.
- mccode-plumber must pass `--hdf-template-prefix` to kafka-to-nexus (branch
  `writer-template-prefix`), so that the writer finds the template in its working
  directory.
- A dataset in the template cannot be changed by a start message, so nothing NICOS sets
  per run (title, users, sample) may be in the structure.
- A sample shares its primary with the others only with mccode-antlr's
  `split-drops-unused-uservars` change and restage's `compile-a-copy`; without the first,
  the split keeps a sample's particle variables in the primary and each new sample
  simulates it again; without the second, every count after a compile does.
- The setup's instrument (`DITTO_INSTRUMENT`) must be built by the same builder, with
  the same niess and mccode-antlr, as `load_sample`'s: one built by other versions
  differs in its primary too (component metadata, number formatting), so it shares no
  primary with the samples.
- `rays_per_charge` is a plain conversion factor; the charge preset is not yet tied to
  the source's real proton charge.

## License

`niess-ditto` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
