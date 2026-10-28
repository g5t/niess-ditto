# niess-ditto

[![PyPI - Version](https://img.shields.io/pypi/v/niess-ditto.svg)](https://pypi.org/project/niess-ditto)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/niess-ditto.svg)](https://pypi.org/project/niess-ditto)

-----

## Table of Contents

- [Installation](#installation)
- [What it provides](#what-it-provides)
- [Usage in a NICOS setup](#usage-in-a-nicos-setup)
- [Changing the sample](#changing-the-sample)
- [Counting through the EFUs](#counting-through-the-efus)
- [Counting through esslivedata](#counting-through-esslivedata)
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
  A chopper speed device counts as the real `Spd_S` does, positive clockwise facing
  away from the source, and sets the simulation's NeXus-signed speed (logged as
  `SpdNexus-R`) to its negation.
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
    model_builder="/opt/ditto/bifrost_phonon.py:ditto_model",
    nicos_setups=[Path(nicos_ess.__file__).parent / "bifrost" / "setups"],
)
```

The setup builds the digital model when NICOS loads it: `model_builder` returns the
NeXus structure and the McStas instrument, written to `<workdir>/model/`. Building the
instrument takes seconds and NICOS evaluates a setup in every process that reads it, so
the files are kept until the builder's source, its `model_options`, niess or
mccode-antlr change. `instrument_json` and `structure_json` give a prebuilt pair instead.

```python
start_filewriting("a3 scan")
maw(incident_band, 4.5)            # meV; or incident_band.set_wavelength_max(3.0)
scan(sample_stack_rotation, 0, 1, 3, charge=100000)
stop_filewriting()
```

The BIFROST builder is `ditto_model` in bifrost-workflow-2609's `bifrost_phonon.py`, whose
`--live --real-pv-names` writes the same pair to files. The setup builds it with
`real_pv_names=True`: the simulated PVs take the real instrument's names, without niess's
`mcstas:` prefix, which is safe because mccode-plumber keeps every EPICS server and client
on the loopback interface.
Needs a Kafka broker, and the stacktainer splitrun image's EFU, forwarder,
kafka-to-nexus and template-maker.

As at ESS, the file-writer starts each file from a template: `sim_services` makes it
from the structure's datasets with kafka-to-nexus' `template-maker` (again only when the
structure changes), and NICOS' start message carries the streams and links only, 176 kB
instead of 1.5 MB for BIFROST.

## Changing the sample

A sample script defines a niess section, `sample`, and the file's NXsample group,
`nexus`. niess's `niess.bifrost.samples` (after 0.15.2) builds the section from McStas' sample components
-- vanadium, powders, tunnelling, spin waves, S(Q,w) tables -- with their focusing on the
analyzers and the elastic monitor done for you, and gives McStas and `nexus` the same
shape (see `examples/`: `vanadium.py`, `alumina.py`, `picoline.py`):

```python
sim_sample.load_sample("examples/vanadium.py")   # ~7 s: the instrument is rebuilt
scan(sample_stack_rotation, 0, 1, 10, charge=100000)
sim_sample.clear_sample()                        # back to the setup's own sample
```

The setup's `DITTO_BUILDER` (`bifrost_phonon.py:ditto_instrument` in
bifrost-workflow-2609) builds the instrument around it. Files started afterwards have
`nexus` as `/entry/sample`, where NICOS adds the Sample device's information too. Its
`depends_on` links to that of `/entry/instrument/sample`, so the sample's orientation
(the logged `sample_rotation`, SQW's psi) can be read from the file; without a loaded
script the group holds only that link. A sample may use fewer of the instrument's parameters, or new ones with defaults; one that
needs a parameter no device sets is refused.

`load_sample` passes keyword arguments to the script as names it already has, so one
script serves every remount. The sample stack can't translate, so a sample is moved the way
it is at the instrument, by remounting it: `examples/small_powder.py` reads `offset`, and
`sample(..., offset=...)` mounts it there:

```python
sim_sample.load_sample("examples/small_powder.py", offset=(0, 0.002, 0))   # 2 mm up
```

A data file McStas ships is named bare (`powder("Al2O3_sapphire.laz", ...)`). One of
your own goes beside the script as a path, `Path(__file__).parent / "mine.laz"`, which
niess writes absolutely, so it does not matter that the simulation runs in NICOS'
working directory.

## Counting through the EFUs

By default a count simulates the primary into McStas monitor histograms, which
mccode-plumber publishes as they are, and only the secondary's detector events go
through the detector EFU. With `DITTO_COLLECT=1` for `nicos/ditto/setups/bifrost.py`, the
monitors go through the beam monitor EFU as well, as the real ones do:

- the model and every sample are built with `collect=True`, so each count collects its
  detector and monitor rays to files instead of sending them live;
- `sim_services` starts the detector and beam monitor EFUs that `DITTO_EFUS`
  (`bifrost_phonon.py:ditto_efus` by default) describes;
- after the count is simulated, `SimDetector` (`replay=True`) replays its files to those
  EFUs in order, over `pulses_per_point` source pulses (at least 14, which the beam
  monitor EFU needs to send its histograms).

```console
DITTO_COLLECT=1 nicos-script -M system,bifrost scan.py
```

The monitors then publish under the beam monitor EFU's own source names (`cbm1` to
`cbm5`), so the setup leaves out `monitor_sources`. Replay times the events with the
count's `charge` divided by `charge_rate` (µC/s), and `replay_seed` fixes the sampling.
`DITTO_SCRIPT` names another `bifrost_phonon.py` for the model, sample and EFU builders
at once.

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

esslivedata must run against the same broker, with `--instrument bifrost`. The logs need
nothing, since the simulated PVs have the real names, and nor do the monitors: the setup's
`monitor_sources` gives each the beam monitor EFU's source (`psc_monitor` publishes as
`cbm1`, ...), as the real instrument's structure does, and mccode-plumber publishes each histogram under its structure's source.

## Known limits

- BIFROST's pulse-shaping and frame-overlap discs turn anticlockwise facing away from
  the source (NeXus-positive), so chopcal sets them to negative `Spd_S` speeds, as the
  chopper group's convention has it. The real setups don't follow that convention yet
  and map only non-negative speeds, so `SimChopperSpeed` accepts either sign of a
  mapped speed, which the real instrument's NICOS does not.
- The services start in NICOS' master process. A session that only becomes master
  after loading the setup (`nicos-script -M`) calls `sim_services.start()` itself.
- The simulation runs in NICOS' working directory, so a sample's data files must be
  named absolutely (see [Changing the sample](#changing-the-sample)); the setup's own lead
  crystal is, from bifrost-workflow-2609's `sample-data-paths`, as long as its `.lau` is
  installed beside `bifrost_phonon.py`.
- A dataset in the template cannot be changed by a start message, so nothing NICOS sets
  per run (title, users, sample) may be in the structure.
- A sample shares its primary with the others only with mccode-antlr's
  `split-drops-unused-uservars` change and restage's `compile-a-copy`; without the first,
  the split keeps a sample's particle variables in the primary and each new sample
  simulates it again; without the second, every count after a compile does.
- The setup's instrument must be built by the same builder script, with
  the same niess and mccode-antlr, as `load_sample`'s: one built by other versions
  differs in its primary too (component metadata, number formatting), so it shares no
  primary with the samples.
- `rays_per_charge` is a plain conversion factor; the charge preset is not yet tied to
  the source's real proton charge.

## License

`niess-ditto` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
