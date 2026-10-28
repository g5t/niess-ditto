"""A vanadium rod: incoherent elastic scattering only, aimed at the analyzers and the
elastic monitor.

    sim_sample.load_sample("examples/vanadium.py")
"""
from niess.bifrost.samples import Cylinder, sample, vanadium

rod = Cylinder(radius=0.005, height=0.02)
sample = sample(vanadium(rod))

nexus = {
    "name": "vanadium rod",
    "chemical_formula": "V",
    "type": "sample",
    "unit_cell_abc": ([3.0399, 3.0399, 3.0399], "angstrom"),
    "unit_cell_alphabetagamma": ([90.0, 90.0, 90.0], "degree"),
    **rod.nexus(),
}
