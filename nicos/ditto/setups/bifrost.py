description = "BIFROST digital model"

from niess_ditto.setup_generator import make_ditto_setup

devices = make_ditto_setup(
  instrument_json='/opt/ditto/bifrost.json'
  broker='localhost:9092',
)
