# niess-ditto

[![PyPI - Version](https://img.shields.io/pypi/v/niess-ditto.svg)](https://pypi.org/project/niess-ditto)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/niess-ditto.svg)](https://pypi.org/project/niess-ditto)

-----

## Table of Contents

- [Installation](#installation)
- [What it provides](#what-it-provides)
- [Usage in a NICOS setup](#usage-in-a-nicos-setup)
- [License](#license)

## Installation

```console
pip install niess-ditto
```

## What it provides

`niess-ditto` provides NICOS device classes and setup helpers for a DITTO digital
instrument model:

- `niess_ditto.state.SimState`: shared in-memory motor-position state
- `niess_ditto.motor.SimMotor`: driveable motor storing targets in `SimState`
- `niess_ditto.detector.SimDetector`: `McStasSimulation` subclass that runs the
  simulation binary
- `niess_ditto.service_manager.SimServiceManager`: manages EFU, EPICS mailbox,
  EPICS forwarder and Kafka-to-Nexus worker processes
- `niess_ditto.setup_generator.make_ditto_setup(...)`: generates a NICOS
  `devices` dict from a mccode-antlr JSON instrument definition

## Usage in a NICOS setup

```python
# nicos_ess/<instrument>/setups/digital_model.py
description = "Digital model"

from niess_ditto.setup_generator import make_ditto_setup

devices = make_ditto_setup(
    instrument_json="/opt/ditto/tsorfib.json",
    broker="localhost:9092",
    rays_per_charge=1.0,
)
```

The generated setup includes:

- a shared state device
- one `SimMotor` per numeric instrument parameter
- one `SimServiceManager` device to start/stop background services
- one `SimDetector` device that converts charge preset to neutron-ray count via
  `rays_per_charge`

## License

`niess-ditto` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
