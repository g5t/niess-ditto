"""A 3x3x3 mm Al2O3 scatterer, for the beryllium filter's acceptance (V&V plan 3.7.2):
remount it off-centre and measure again, as at the real instrument, where nothing
translates the sample.

    for y in (-0.004, -0.002, 0.0, 0.002, 0.004):          # metres, upwards
        sim_sample.load_sample("examples/small_powder.py", offset=(0, y, 0))
        count(charge=100000)

``offset`` is in the sample stack's frame: at zero sample_rotation x is across the beam,
y up and z along it. Without one the scatterer is centred.
"""
from niess.bifrost.samples import Box, powder, sample

offset = globals().get("offset", (0.0, 0.0, 0.0))
cube = Box(width=0.003, height=0.003, depth=0.003)
sample = sample(powder("Al2O3_sapphire.laz", cube), offset=offset)

nexus = {
    "name": "small alumina scatterer",
    "chemical_formula": "Al2O3",
    "type": "calibration sample",
    "mounting_offset": ([float(x) for x in offset], "m"),
    **cube.nexus(),
}
