from types import SimpleNamespace as NS

from niess_ditto.chopper import SimChopperSpeed


def test_a_speed_may_take_either_sign_of_a_mapped_one():
    psc = NS(speeds=[0.0, 14.0, 126.0])
    assert SimChopperSpeed.doIsAllowed(psc, -126.0)[0]
    assert SimChopperSpeed.doIsAllowed(psc, 126.0)[0]
    assert not SimChopperSpeed.doIsAllowed(psc, -100.0)[0]
