import pytest

from niess_ditto.translator import record, translate


def _log(parameter, source):
    return {
        "type": "group", "name": parameter,
        "attributes": [{"name": "NX_class", "values": "NXlog"},
                       {"name": "simulation_parameter", "values": parameter}],
        "children": [{"module": "f144",
                      "config": {"source": source, "topic": "t", "dtype": "double"}}],
    }


STRUCTURE = {"children": [{
    "type": "group", "name": "entry",
    "attributes": [{"name": "NX_class", "values": "NXentry"}],
    "children": [
        _log("sample_rotation", "mcstas:BIFRO-SpRot:MC-RotZ-01:Mtr.RBV"),
        _log("pulse_shaping_chopper_1_rotation_speed", "mcstas:BIFRO-ChpSy1:Chop-PSC-101:Spd_R"),
        _log("mask_left", "mcstas:mask_left"),
    ],
}]}

SETUPS = {
    "sample_stack_rotation": ("nicos_ess.devices.epics.motor.EpicsMotor",
                              {"motorpv": "BIFRO-SpRot:MC-RotZ-01:Mtr"}),
    "psc1_chopper_speed": ("nicos_ess.devices.epics.pva.EpicsManualMappedAnalogMoveable",
                           {"readpv": "BIFRO-ChpSy1:Chop-PSC-101:Spd_R",
                            "writepv": "BIFRO-ChpSy1:Chop-PSC-101:Spd_S"}),
    "psc1_chopper": ("nicos_ess.devices.epics.chopper.NewEssChopperController",
                     {"speed": "psc1_chopper_speed"}),
    "sample_stack_rotation_temp": ("nicos_ess.devices.epics.pva.EpicsReadable",
                                   {"readpv": "BIFRO-SpRot:MC-RotZ-01:Mtr-Temp"}),
}


def test_record_drops_prefix_and_field():
    assert record("mcstas:BIFRO-SpRot:MC-RotZ-01:Mtr.RBV") == "BIFRO-SpRot:MC-RotZ-01:Mtr"
    assert record("BIFRO-ChpSy1:Chop-PSC-101:ChopDly-S") == "BIFRO-ChpSy1:Chop-PSC-101:ChopDly-S"


def test_devices_match_parameters_by_pv():
    found = translate(STRUCTURE, SETUPS)
    assert found.parameters == {
        "sample_stack_rotation": "sample_rotation",
        "psc1_chopper_speed": "pulse_shaping_chopper_1_rotation_speed",
    }
    assert found.controllers == {"psc1_chopper": "psc1_chopper_speed"}
    assert found.device_of("mask_left") is None


def test_two_devices_for_one_parameter_is_an_error():
    setups = dict(SETUPS, a3=("x.EpicsMotor", {"motorpv": "BIFRO-SpRot:MC-RotZ-01:Mtr"}))
    with pytest.raises(ValueError, match="set by both"):
        translate(STRUCTURE, setups)
