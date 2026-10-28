"""Al2O3 powder in a 3 mm capillary, for the scattering-angle and flight-path calibrations.

    sim_sample.load_sample("examples/alumina.py")

McStas ships the reflection list, so it is named bare. A file of your own goes beside
this script and is given as a path, which is written absolutely::

    powder(Path(__file__).parent / "mine.laz", capillary)
"""
from niess.bifrost.samples import Cylinder, powder, sample

capillary = Cylinder(radius=0.0015, height=0.02)
sample = sample(powder("Al2O3_sapphire.laz", capillary))

nexus = {
    "name": "alumina powder",
    "chemical_formula": "Al2O3",
    "type": "calibration sample",
    "unit_cell_abc": ([4.759, 4.759, 12.992], "angstrom"),
    "unit_cell_alphabetagamma": ([90.0, 90.0, 120.0], "degree"),
    **capillary.nexus(),
}
