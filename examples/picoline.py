"""gamma-picoline-N-oxide: methyl tunnelling lines at +-32 ueV beside the elastic line,
far narrower than BIFROST's resolution, for the energy resolution near the elastic line.

    sim_sample.load_sample("examples/picoline.py")
"""
from niess.bifrost.samples import Box, sample, tunneling

slab = Box(width=0.02, height=0.02, depth=0.002)
# per molecule: seven hydrogens' incoherent scattering, and ~165 A^3 (109 g/mol, ~1.1 g/cm3)
sample = sample(tunneling(slab, E_tun=0.032, f_tun=0.6,
                          sigma_inc=562.0, sigma_abs=4.3, Vc=165.0))

nexus = {
    "name": "gamma-picoline-N-oxide",
    "chemical_formula": "C6H7NO",
    "type": "sample",
    **slab.nexus(),
}
