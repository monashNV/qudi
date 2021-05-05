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

    def __init__(self):
        pass

    def on_deactivate(self):
