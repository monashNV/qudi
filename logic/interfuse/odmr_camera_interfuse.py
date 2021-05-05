# -*- coding: utf-8 -*-

"""
This file contains the Qudi Interfuse between a laser interface and analog output of a confocal_scanner_interface
 to control an analog driven AOM (Acousto-optic modulator).

---

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""
import numpy as np

from core.connector import Connector
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic

from interface.odmr_counter_interface import ODMRCounterInterface
from interface.microwave_interface import MicrowaveInterface
from interface.pulser_interface import PulserInterface
from interface.microwave_interface import TriggerEdge

from interface.camera_interface import CameraInterface

class ODMRCameraInterfuse(GenericLogic, MicrowaveInterface, CameraInterface, PulserInterface):

    """
    Interfuse, applies microwaves and acquires a series of images from a Camera
    this pretends it is like an ODMRCounterInterface
    Also, we don't need to use the NI card as a clock/counter so we just use a pulse generator instead
    """

    camera = Connector(interface='CameraInterface')
    mw = Connector(interface='MicrowaveInterface')
    pulser = Connector(interface='PulserInterface')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        self.camera = self.camera()
        self.mw = self.mw()
        self.pulser = self.pulser()

    def on_deactivate(self):
        pass

    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        """ clock goes to camera trigger

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """
        self.clock_frequency = clock_frequency
        self.clock_channel = clock_channel
        return 0

    def set_odmr_length(self, length=100):
        """Set up the trigger sequence for the ODMR and the triggered microwave.

        @param int length: length of microwave sweep in pixel

        @return int: error code (0:OK, -1:error)
        """
        self.odmr_length = length
        return 0

    def set_up_odmr(self, counter_channel=None, photon_source=None,
                    clock_channel=None, odmr_trigger_channel=None):
        """ Configures the actual counter with a given clock.

        @param str counter_channel: if defined, this is the physical channel of
                                    the counter
        @param str photon_source: if defined, this is the physical channel where
                                  the photons are to count from
        @param str clock_channel: if defined, this specifies the clock for the
                                  counter
        @param str odmr_trigger_channel: if defined, this specifies the trigger
                                         output for the microwave

        @return int: error code (0:OK, -1:error)
        """

        # Set up the camera ... not sure what goes here yet
        # We either want kinetic series or run until abort acqusition mods

        # The pulse sequence should be trigger+acquire together, with mw_x always on
        self.pulser.write_waveform()
        self.pulser.load_waveform()

        pass

    def count_odmr(self, length = 100):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return (bool, float[]): tuple: was there an error, the photon counts per second
        """
        pass
