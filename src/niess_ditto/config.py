from nicos.core import Device, Param


class SimInstrumentConfig(Device):
    """Holds instrument configuration parameters (string-valued) for DITTO setups.
    
    Allows users to modify non-numeric McStas parameters at runtime, such as
    filenames, seed values, etc.
    """

    parameters = {}  # Dynamically populated by make_ditto_setup()

    def doInit(self, mode):
        # Parameters are set by the setup generator, nothing special to do
        Device.doInit(self, mode)
