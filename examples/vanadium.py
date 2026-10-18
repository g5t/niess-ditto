"""A vanadium rod: incoherent elastic scattering only, aimed at the detector tank.

    sim_sample.load_sample("examples/vanadium.py")
"""
from niess.components import Opaque, Section
from scipp import vector
from scipp.spatial import rotations_from_rotvecs


class Vanadium(Section):
    rod: Opaque


# The tank turns about the lab by detector_tank_angle and this frame by sample_rotation,
# so it is in the direction of their difference here; it is 90 degrees wide, 3 high.
toward_tank = "DEG2RAD * (detector_tank_angle - sample_rotation)"
sample = Vanadium(rod=Opaque(
    name="vanadium", mccode_type="Incoherent",
    mccode_parameters={
        "radius": 0.005, "yheight": 0.02, "focus_aw": 90.0, "focus_ah": 3.0,
        "target_x": f"sin({toward_tank})", "target_y": 0.0, "target_z": f"cos({toward_tank})",
    },
    position=vector([0., 0., 0.], unit="m"),
    orientation=rotations_from_rotvecs(vector([0., 0., 0.], unit="deg")),
))

nexus = {
    "name": "vanadium rod",
    "chemical_formula": "V",
    "type": "sample",
    "unit_cell_abc": ([3.0399, 3.0399, 3.0399], "angstrom"),
    "unit_cell_alphabetagamma": ([90.0, 90.0, 90.0], "degree"),
    "radius": (0.005, "m"),
    "height": (0.02, "m"),
}
