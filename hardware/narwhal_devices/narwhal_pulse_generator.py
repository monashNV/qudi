# -*- coding: utf-8 -*-

"""
This file contains the Qudi hardware interface for pulsing devices.

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

from core.module import Base
from core.configoption import ConfigOption
from core.statusvariable import  StatusVar
from core.util.modules import get_home_dir
from interface.pulser_interface import PulserInterface, PulserConstraints
from collections import OrderedDict
import numpy as np
import re

import ndpulsegen
import time


class PulseGenerator(Base, PulserInterface):
    """ Methods to control the Narwhal devices pulsegenerator

    Example config for copy-paste:

    pulsestreamer:
        module.Class: 'swabian_instruments.pulse_streamer.PulseStreamer'
        pulsestreamer_ip: '192.168.1.100'
        #pulsed_file_dir: 'C:\\Software\\pulsed_files'
        laser_channel: 0
        uw_x_channel: 1
        use_external_clock: False
        external_clock_option: 0
    """

    _current_waveform = StatusVar(name='current_waveform', default={})
    _current_waveform_name = StatusVar(name='current_waveform_name', default='')
    _sample_rate = StatusVar(name='sample_rate', default=100e6)

    _laser_channel = ConfigOption('laser_channel', default=0, missing='warn')
    _mw_x_channel = ConfigOption('mw_x_channel', default=1, missing='warn')
    _mw_xb_channel = ConfigOption('mw_xb_channel', default=2, missing='warn')
    _mw_y_channel = ConfigOption('mw_y_channel', default=3, missing='warn')
    _mw_yb_channel = ConfigOption('mw_yb_channel', default=4, missing='warn')
    _odmr_freq_step_trigger = ConfigOption('odmr_freq_step_trigger', default=5, missing='warn')
    _camera_trigger = ConfigOption('camera_trigger', default=6, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self._current_status = -1
        self._currently_loaded_waveform = ''  # loaded and armed waveform name
        self._samples_written = 0
        self._trigger = 'software'
        self._max_instructions = int(2**13)
        self._waveforms = dict()
        self._free_memory = np.ones(self._max_instructions).astype(np.bool_)

    def on_activate(self):
        """ Establish connection to pulse generator and tell it to cancel all operations """

        self.pg = ndpulsegen.PulseGenerator()
        assert self.pg.connect_serial(), 'Failed to connect to Narwhal Pulse Generator'

        self._samples_written = 0
        self._currently_loaded_waveform = ''

    def on_deactivate(self):
        self.pg.close_serial_read_thread()

    def get_constraints(self):
        """
        Retrieve the hardware constrains from the Pulsing device.

        @return constraints object: object with pulser constraints as attributes.

        Provides all the constraints (e.g. sample_rate, amplitude, total_length_bins,
        channel_config, ...) related to the pulse generator hardware to the caller.

            SEE PulserConstraints CLASS IN pulser_interface.py FOR AVAILABLE CONSTRAINTS!!!

        If you are not sure about the meaning, look in other hardware files to get an impression.
        If still additional constraints are needed, then they have to be added to the
        PulserConstraints class.

        Each scalar parameter is an ScalarConstraints object defined in core.util.interfaces.
        Essentially it contains min/max values as well as min step size, default value and unit of
        the parameter.

        PulserConstraints.activation_config differs, since it contain the channel
        configuration/activation information of the form:
            {<descriptor_str>: <channel_set>,
             <descriptor_str>: <channel_set>,
             ...}

        If the constraints cannot be set in the pulsing hardware (e.g. because it might have no
        sequence mode) just leave it out so that the default is used (only zeros).

        # Example for configuration with default values:
        constraints = PulserConstraints()

        constraints.sample_rate.min = 10.0e6
        constraints.sample_rate.max = 12.0e9
        constraints.sample_rate.step = 10.0e6
        constraints.sample_rate.default = 12.0e9

        constraints.a_ch_amplitude.min = 0.02
        constraints.a_ch_amplitude.max = 2.0
        constraints.a_ch_amplitude.step = 0.001
        constraints.a_ch_amplitude.default = 2.0

        constraints.a_ch_offset.min = -1.0
        constraints.a_ch_offset.max = 1.0
        constraints.a_ch_offset.step = 0.001
        constraints.a_ch_offset.default = 0.0

        constraints.d_ch_low.min = -1.0
        constraints.d_ch_low.max = 4.0
        constraints.d_ch_low.step = 0.01
        constraints.d_ch_low.default = 0.0

        constraints.d_ch_high.min = 0.0
        constraints.d_ch_high.max = 5.0
        constraints.d_ch_high.step = 0.01
        constraints.d_ch_high.default = 5.0

        constraints.waveform_length.min = 80
        constraints.waveform_length.max = 64800000
        constraints.waveform_length.step = 1
        constraints.waveform_length.default = 80

        constraints.waveform_num.min = 1
        constraints.waveform_num.max = 32000
        constraints.waveform_num.step = 1
        constraints.waveform_num.default = 1

        constraints.sequence_num.min = 1
        constraints.sequence_num.max = 8000
        constraints.sequence_num.step = 1
        constraints.sequence_num.default = 1

        constraints.subsequence_num.min = 1
        constraints.subsequence_num.max = 4000
        constraints.subsequence_num.step = 1
        constraints.subsequence_num.default = 1

        # If sequencer mode is available then these should be specified
        constraints.repetitions.min = 0
        constraints.repetitions.max = 65539
        constraints.repetitions.step = 1
        constraints.repetitions.default = 0

        constraints.event_triggers = ['A', 'B']
        constraints.flags = ['A', 'B', 'C', 'D']

        constraints.sequence_steps.min = 0
        constraints.sequence_steps.max = 8000
        constraints.sequence_steps.step = 1
        constraints.sequence_steps.default = 0

        # the name a_ch<num> and d_ch<num> are generic names, which describe UNAMBIGUOUSLY the
        # channels. Here all possible channel configurations are stated, where only the generic
        # names should be used. The names for the different configurations can be customary chosen.
        activation_conf = OrderedDict()
        activation_conf['yourconf'] = {'a_ch1', 'd_ch1', 'd_ch2', 'a_ch2', 'd_ch3', 'd_ch4'}
        activation_conf['different_conf'] = {'a_ch1', 'd_ch1', 'd_ch2'}
        activation_conf['something_else'] = {'a_ch2', 'd_ch3', 'd_ch4'}
        constraints.activation_config = activation_conf
        """
        constraints = PulserConstraints()

        # The file formats are hardware specific.

        constraints.sample_rate.min = 100e6
        constraints.sample_rate.max = 100e6
        constraints.sample_rate.step = 0
        constraints.sample_rate.default = 100e6
        constraints.sample_rate.unit = 'Hz'

        constraints.d_ch_low.min = 0.0
        constraints.d_ch_low.max = 0.0
        constraints.d_ch_low.step = 0.0
        constraints.d_ch_low.default = 0.0
        constraints.d_ch_low.unit = 'V'

        constraints.d_ch_high.min = 3.3
        constraints.d_ch_high.max = 3.3
        constraints.d_ch_high.step = 0.0
        constraints.d_ch_high.default = 3.3
        constraints.d_ch_low.unit = 'V'

        constraints.waveform_length.min = 1
        constraints.waveform_length.max = 2**48-1 # max delay length in clock units
        constraints.waveform_length.step = 1
        constraints.waveform_length.default = 1

        # the name a_ch<num> and d_ch<num> are generic names, which describe UNAMBIGUOUSLY the
        # channels. Here all possible channel configurations are stated, where only the generic
        # names should be used. The names for the different configurations can be customary chosen.
        activation_config = OrderedDict()
        activation_config['all'] = frozenset({'d_ch1', 'd_ch2', 'd_ch3', 'd_ch4', 'd_ch5', 'd_ch6', 'd_ch7', 'd_ch8',
                                              'd_ch9', 'd_ch10', 'd_ch11', 'd_ch12', 'd_ch13', 'd_ch14', 'd_ch15', 'd_ch16',
                                              'd_ch17', 'd_ch18', 'd_ch19', 'd_ch20', 'd_ch21', 'd_ch22', 'd_ch23', 'd_ch24'})
        constraints.activation_config = activation_config

        return constraints
    
    def pulser_on(self):
        """ Switches the pulsing device on.

        @return int: error code (0:OK, -1:error)
        """
        if True: #Should be something here
            self.pg.write_action(trigger_now=True)
            return 0
        else:
            self.log.error('no sequence/pulse pattern prepared for the pulse streamer')
            self._current_status = -1
            return -1
    
    def pulser_off(self):
        """ Switches the pulsing device off.

        @return int: error code (0:OK, -1:error)
        """

        self.pg.write_action(reset_output_coordinator=True)
        return 0

    def _laser_on(self):
        self.pg.write_action(reset_output_coordinator=True)
        self.pg.write_static_state(int(self._laser_channel))
    
    def load_waveform(self, load_dict):
        """ Loads a waveform to the specified channel of the pulsing device.

        @param dict|list load_dict: a dictionary with keys being one of the available channel
                                    index and values being the name of the already written
                                    waveform to load into the channel.
                                    Examples:   {1: rabi_ch1, 2: rabi_ch2} or
                                                {1: rabi_ch2, 2: rabi_ch1}
                                    If just a list of waveform names if given, the channel
                                    association will be invoked from the channel
                                    suffix '_ch1', '_ch2' etc.

                                        {1: rabi_ch1, 2: rabi_ch2}
                                    or
                                        {1: rabi_ch2, 2: rabi_ch1}

                                    If just a list of waveform names if given,
                                    the channel association will be invoked from
                                    the channel suffix '_ch1', '_ch2' etc. A
                                    possible configuration can be e.g.

                                        ['rabi_ch1', 'rabi_ch2', 'rabi_ch3']

        @return dict: Dictionary containing the actually loaded waveforms per
                      channel.

        For devices that have a workspace (i.e. AWG) this will load the waveform
        from the device workspace into the channel. For a device without mass
        memory, this will make the waveform/pattern that has been previously
        written with self.write_waveform ready to play.

        Please note that the channel index used here is not to be confused with the number suffix
        in the generic channel descriptors (i.e. 'd_ch1', 'a_ch1'). The channel index used here is
        highly hardware specific and corresponds to a collection of digital and analog channels
        being associated to a SINGLE waveform asset.
        """
        if isinstance(load_dict, list):
            waveforms = list(set(load_dict))
        elif isinstance(load_dict, dict):
            waveforms = list(set(load_dict.values()))
        else:
            self.log.error('Method load_waveform expects a list of waveform names or a dict.')
            return self.get_loaded_assets()[0]

        if len(waveforms) != 1:
            self.log.error('pulsestreamer pulser expects exactly one waveform name for load_waveform.')
            return self.get_loaded_assets()[0]

        waveform = waveforms[0]
        if waveform != self._current_waveform_name:
            self.log.error('No waveform by the name "{0}" generated for pulsestreamer pulser.\n'
                           'Only one waveform at a time can be held.'.format(waveform))
            return self.get_loaded_assets()[0]

        self._seq = self.pulse_streamer.createSequence()
        for channel_number, pulse_pattern in self._current_waveform.items():
            swabian_channel_number = int(channel_number[-1])-1
            self._seq.setDigital(swabian_channel_number,pulse_pattern)

        self._currently_loaded_waveform = self._current_waveform_name
        return self.get_loaded_assets()[0]


    def get_loaded_assets(self):
        """
        Retrieve the currently loaded asset names for each active channel of the device.
        The returned dictionary will have the channel numbers as keys.
        In case of loaded waveforms the dictionary values will be the waveform names.
        In case of a loaded sequence the values will be the sequence name appended by a suffix
        representing the track loaded to the respective channel (i.e. '<sequence_name>_1').

        @return (dict, str): Dictionary with keys being the channel number and values being the
                             respective asset loaded into the channel,
                             string describing the asset type ('waveform' or 'sequence')
        """
        asset_type = 'waveform' if self._currently_loaded_waveform else None
        asset_dict = {chnl_num: self._currently_loaded_waveform for chnl_num in range(1, 9)}
        return asset_dict, asset_type

    
    def load_sequence(self, sequence_name):
        """ Loads a sequence to the channels of the device in order to be ready for playback.
        For devices that have a workspace (i.e. AWG) this will load the sequence from the device
        workspace into the channels.
        For a device without mass memory this will make the waveform/pattern that has been
        previously written with self.write_waveform ready to play.

        @param dict|list sequence_name: a dictionary with keys being one of the available channel
                                        index and values being the name of the already written
                                        waveform to load into the channel.
                                        Examples:   {1: rabi_ch1, 2: rabi_ch2} or
                                                    {1: rabi_ch2, 2: rabi_ch1}
                                        If just a list of waveform names if given, the channel
                                        association will be invoked from the channel
                                        suffix '_ch1', '_ch2' etc.

        @return dict: Dictionary containing the actually loaded waveforms per channel.
        """
        self.log.debug('sequencing not implemented for pulsestreamer')
        return dict()


    def clear_all(self):
        """ Clears all loaded waveforms from the pulse generators RAM/workspace.

        @return int: error code (0:OK, -1:error)
        """
        self.pulser_off()
        self._currently_loaded_waveform = ''
        self._current_waveform_name = ''
        self._seq = dict()
        self._current_waveform = dict()

    def get_status(self):
        """ Retrieves the status of the pulsing hardware

        @return (int, dict): tuple with an integer value of the current status and a corresponding
                             dictionary containing status description for all the possible status
                             variables of the pulse generator hardware.
        """
        status_dic = dict()
        status_dic[-1] = 'Failed Request or Failed Communication with device.'
        status_dic[0] = 'Device has stopped, but can receive commands.'
        status_dic[1] = 'Device is active and running.'

        return self.__current_status, status_dic

    
    def get_sample_rate(self):
        """ Get the sample rate of the pulse generator hardware

        @return float: The current sample rate of the device (in Hz)

        Do not return a saved sample rate in a class variable, but instead
        retrieve the current sample rate directly from the device.
        """
        return self._sample_rate

    def set_sample_rate(self, sample_rate):
        """ Set the sample rate of the pulse generator hardware.

        @param float sample_rate: The sampling rate to be set (in Hz)

        @return float: the sample rate returned from the device.

        Note: After setting the sampling rate of the device, retrieve it again
              for obtaining the actual set value and use that information for
              further processing.
        """
        self.log.debug('PulseGenerator sample rate cannot be configured')
        return self._sample_rate

    def get_analog_level(self, amplitude=None, offset=None):
        """ Retrieve the analog amplitude and offset of the provided channels.

        @param list amplitude: optional, if the amplitude value (in Volt peak to peak, i.e. the
                               full amplitude) of a specific channel is desired.
        @param list offset: optional, if the offset value (in Volt) of a specific channel is
                            desired.

        @return: (dict, dict): tuple of two dicts, with keys being the channel descriptor string
                               (i.e. 'a_ch1') and items being the values for those channels.
                               Amplitude is always denoted in Volt-peak-to-peak and Offset in volts.

        Note: Do not return a saved amplitude and/or offset value but instead retrieve the current
              amplitude and/or offset directly from the device.

        If nothing (or None) is passed then the levels of all channels will be returned. If no
        analog channels are present in the device, return just empty dicts.

        Example of a possible input:
            amplitude = ['a_ch1', 'a_ch4'], offset = None
        to obtain the amplitude of channel 1 and 4 and the offset of all channels
            {'a_ch1': -0.5, 'a_ch4': 2.0} {'a_ch1': 0.0, 'a_ch2': 0.0, 'a_ch3': 1.0, 'a_ch4': 0.0}
        """
        return {}, {}

    def set_analog_level(self, amplitude=None, offset=None):
        """ Set amplitude and/or offset value of the provided analog channel(s).

        @param dict amplitude: dictionary, with key being the channel descriptor string
                               (i.e. 'a_ch1', 'a_ch2') and items being the amplitude values
                               (in Volt peak to peak, i.e. the full amplitude) for the desired
                               channel.
        @param dict offset: dictionary, with key being the channel descriptor string
                            (i.e. 'a_ch1', 'a_ch2') and items being the offset values
                            (in absolute volt) for the desired channel.

        @return (dict, dict): tuple of two dicts with the actual set values for amplitude and
                              offset for ALL channels.

        If nothing is passed then the command will return the current amplitudes/offsets.

        Note: After setting the amplitude and/or offset values of the device, use the actual set
              return values for further processing.
        """
        return {}, {}

    def get_digital_level(self, low=None, high=None):

        """ Retrieve the digital low and high level of the provided channels.

        @param list low: optional, if a specific low value (in Volt) of a
                         channel is desired.
        @param list high: optional, if a specific high value (in Volt) of a
                          channel is desired.

        @return: (dict, dict): tuple of two dicts, with keys being the channel
                               number and items being the values for those
                               channels. Both low and high value of a channel is
                               denoted in (absolute) Voltage.

        Note: Do not return a saved low and/or high value but instead retrieve
              the current low and/or high value directly from the device.

        If no entries provided then the levels of all channels where simply
        returned. If no digital channels provided, return just an empty dict.

        Example of a possible input:
            low = [1,4]
        to obtain the low voltage values of digital channel 1 an 4. A possible
        answer might be
            {1: -0.5, 4: 2.0} {}
        since no high request was performed.

        The major difference to analog signals is that digital signals are
        either ON or OFF, whereas analog channels have a varying amplitude
        range. In contrast to analog output levels, digital output levels are
        defined by a voltage, which corresponds to the ON status and a voltage
        which corresponds to the OFF status (both denoted in (absolute) voltage)

        In general there is no bijective correspondence between
        (amplitude, offset) and (value high, value low)!
        """

        if low is None:
            low = []
        if high is None:
            high = []
        low_dict = {}
        high_dict = {}
        if low is [] and high is []:
            for channel in range(8):
                low_dict[channel] = 0.0
                high_dict[channel] = 3.3
        else:
            for channel in low:
                low_dict[channel] = 0.0
            for channel in high:
                high_dict[channel] = 3.3
        return low_dict, high_dict

    def set_digital_level(self, low=None, high=None):
        """ Set low and/or high value of the provided digital channel.

        @param dict low: dictionary, with key being the channel and items being
                         the low values (in volt) for the desired channel.
        @param dict high: dictionary, with key being the channel and items being
                         the high values (in volt) for the desired channel.

        @return (dict, dict): tuple of two dicts where first dict denotes the
                              current low value and the second dict the high
                              value.

        If nothing is passed then the command will return two empty dicts.

        Note: After setting the high and/or low values of the device, retrieve
              them again for obtaining the actual set value(s) and use that
              information for further processing.

        The major difference to analog signals is that digital signals are
        either ON or OFF, whereas analog channels have a varying amplitude
        range. In contrast to analog output levels, digital output levels are
        defined by a voltage, which corresponds to the ON status and a voltage
        which corresponds to the OFF status (both denoted in (absolute) voltage)

        In general there is no bijective correspondence between
        (amplitude, offset) and (value high, value low)!
        """
        if low is None:
            low = {}
        if high is None:
            high = {}
        self.log.warning('PulseStreamer logic level cannot be adjusted!')
        return self.get_digital_level()

    def get_active_channels(self, ch=None):
        """ Get the active channels of the pulse generator hardware.

        @param list ch: optional, if specific analog or digital channels are needed to be asked
                        without obtaining all the channels.

        @return dict:  where keys denoting the channel string and items boolean expressions whether
                       channel are active or not.

        Example for an possible input (order is not important):
            ch = ['a_ch2', 'd_ch2', 'a_ch1', 'd_ch5', 'd_ch1']
        then the output might look like
            {'a_ch2': True, 'd_ch2': False, 'a_ch1': False, 'd_ch5': True, 'd_ch1': False}

        If no parameter (or None) is passed to this method all channel states will be returned.
        """
        if ch is None:
            ch = {}
        d_ch_dict = {}
        if len(ch) < 1:
            for chnl in range(1, 24):
                d_ch_dict['d_ch{0}'.format(chnl)] = True
        else:
            for channel in ch:
                d_ch_dict[channel] = True
        return d_ch_dict
    
    def set_active_channels(self, ch=None):
        """
        Set the active/inactive channels for the pulse generator hardware.
        The state of ALL available analog and digital channels will be returned
        (True: active, False: inactive).
        The actually set and returned channel activation must be part of the available
        activation_configs in the constraints.
        You can also activate/deactivate subsets of available channels but the resulting
        activation_config must still be valid according to the constraints.
        If the resulting set of active channels can not be found in the available
        activation_configs, the channel states must remain unchanged.

        @param dict ch: dictionary with keys being the analog or digital string generic names for
                        the channels (i.e. 'd_ch1', 'a_ch2') with items being a boolean value.
                        True: Activate channel, False: Deactivate channel

        @return dict: with the actual set values for ALL active analog and digital channels

        If nothing is passed then the command will simply return the unchanged current state.

        Note: After setting the active channels of the device, use the returned dict for further
              processing.

        Example for possible input:
            ch={'a_ch2': True, 'd_ch1': False, 'd_ch3': True, 'd_ch4': True}
        to activate analog channel 2 digital channel 3 and 4 and to deactivate
        digital channel 1. All other available channels will remain unchanged.
        """
        if ch is None:
            ch = {}
        d_ch_dict = {
            'd_ch1': True,
            'd_ch2': True,
            'd_ch3': True,
            'd_ch4': True,
            'd_ch5': True,
            'd_ch6': True,
            'd_ch7': True,
            'd_ch8': True,
            'd_ch9': True,
            'd_ch10': True,
            'd_ch11': True,
            'd_ch12': True,
            'd_ch13': True,
            'd_ch14': True,
            'd_ch15': True,
            'd_ch16': True,
            'd_ch17': True,
            'd_ch18': True,
            'd_ch19': True,
            'd_ch20': True,
            'd_ch21': True,
            'd_ch22': True,
            'd_ch23': True,
            'd_ch24': True,
        }
        return d_ch_dict

    def make_instructions_from_digital_samples(self, digital_samples):

        """
        Takes the qudi digital samples (dict of sample rate spaced bool value arrays) and creates the times and
        bit values for programming a Narwhal (or SpinCore) device

        @param dict digital_samples: keys are the generic digital channel names (i.e. 'd_ch1') and
                                     values are 1D numpy arrays of type bool containing the marker
                                     states.

        @return (np.array, np.array, int): the times and bits of the instruction list and the number of samples in qudi
        sample rate
        """

        num_channels = len(digital_samples)

        # group everything into a single array
        channel_labels = []
        for i, channel_key in enumerate(digital_samples):
            if i == 0:
                channel_array = digital_samples[channel_key]
                number_of_samples = len(channel_array)
            else:
                channel_array = np.vstack((channel_array, digital_samples[channel_key]))

            # in Narwhal channel units i.e. zero-based
            channel_labels.append(int(re.search(r'd_ch(\d+)', channel_key).group(1))-1)

        # resort the channel array by Narwhal units channel index -> [0,1,2,3,4,5,...23]
        channel_array[:, :] = channel_array[np.argsort(channel_labels), :]

        # Add row before and after array to make row-wise comparisons easier
        channel_array = np.insert(channel_array, 0, np.zeros(num_channels).astype(np.bool_), axis=1)
        channel_array = np.insert(channel_array, number_of_samples, np.zeros(num_channels).astype(np.bool_), axis=1)

        # find if previous step is different
        diffs = np.logical_xor(channel_array[:, 1:], channel_array[:, :-1])
        # is there a difference in any channel?
        diffs = np.any(diffs, axis=0)
        # find the location of the differences
        locations = np.where(diffs)[0]
        # get the values of the channels at the change
        bits = channel_array[:, locations]
        # the first column of channel_array is actually lowest bit, so need to flip the order
        bits = np.packbits(bits, axis=0, bitorder='little')
        # times are already in clock units (steps)
        times = locations
        times = np.insert(times, 0, 0)
        # duration of the instruction is the difference in the times
        times = times[1:]-times[:-1]

        return times, bits, number_of_samples

    def write_waveform(self, name, analog_samples, digital_samples, is_first_chunk, is_last_chunk,
                       total_number_of_samples):
        """
        Write a new waveform or append samples to an already existing waveform on the device memory.
        The flags is_first_chunk and is_last_chunk can be used as indicator if a new waveform should
        be created or if the write process to a waveform should be terminated.

        NOTE: All sample arrays in analog_samples and digital_samples must be of equal length!

        @param str name: the name of the waveform to be created/append to
        @param dict analog_samples: keys are the generic analog channel names (i.e. 'a_ch1') and
                                    values are 1D numpy arrays of type float32 containing the
                                    voltage samples.
        @param dict digital_samples: keys are the generic digital channel names (i.e. 'd_ch1') and
                                     values are 1D numpy arrays of type bool containing the marker
                                     states.
        @param bool is_first_chunk: Flag indicating if it is the first chunk to write.
                                    If True this method will create a new empty waveform.
                                    If False the samples are appended to the existing waveform.
        @param bool is_last_chunk:  Flag indicating if it is the last chunk to write.
                                    Some devices may need to know when to close the appending wfm.
        @param int total_number_of_samples: The number of sample points for the entire waveform
                                            (not only the currently written chunk)

        @return (int, list): Number of samples written (-1 indicates failed process) and list of
                             created waveform names
        """

        if analog_samples:
            self.log.debug('Narwhal has no analog outputs')
            return -1, list()

        if is_first_chunk:

            self._waveforms[name] = dict()
            self._samples_written = 0

            times, bits, number_of_samples = self.make_instructions_from_digital_samples(digital_samples)
            num_instructions = len(bits)
            # find a suitable length chunk of instruction memory
            for start in range(self._max_instructions):
                if self._free_memory[start:start+num_instructions].all():
                    self._waveforms[name]['start_memory'] = start
                    self._free_memory[start:start+num_instructions] = False
                    break
            else:
                self.log.error('Not enough available instruction memory for waveform: {0}'.format(name))

            self._waveforms[name]['instructions'] = []
            for mi in range(num_instructions):
                # address, state, countdown, loopto_address, loops, stop_and_wait_tag, hard_trig_out_tag, notify_computer_tag
                self._waveforms[name]['instructions'].append(ndpulsegen.transcode.encode_instruction(mi + self._waveforms[name]['start_memory'],
                                                             bits[mi], times[mi], 0, 0, False, False, False))

        else:
            pass


        return number_of_samples, [self._current_waveform_name]


    
    def write_sequence(self, name, sequence_parameters):
        """
        Write a new sequence on the device memory.

        @param str name: the name of the waveform to be created/append to
        @param list sequence_parameters: List containing tuples of length 2. Each tuple represents
                                         a sequence step. The first entry of the tuple is a list of
                                         waveform names (str); one for each channel. The second
                                         tuple element is a SequenceStep instance containing the
                                         sequencing parameters for this step.

        @return: int, number of sequence steps written (-1 indicates failed process)
        """
        self.log.debug('Sequencing not yet implemented for pulse streamer')
        return -1

    def get_waveform_names(self):
        """ Retrieve the names of all uploaded waveforms on the device.

        @return list: List of all uploaded waveform name strings in the device workspace.
        """
        waveform_names = list()
        if self._current_waveform_name != '' and self._current_waveform_name is not None:
            waveform_names = [self.__current_waveform_name]
        return waveform_names

    def get_sequence_names(self):
        """ Retrieve the names of all uploaded sequence on the device.

        @return list: List of all uploaded sequence name strings in the device workspace.
        """
        return list()

    def delete_waveform(self, waveform_name):
        """ Delete the waveform with name "waveform_name" from the device memory.

        @param str waveform_name: The name of the waveform to be deleted
                                  Optionally a list of waveform names can be passed.

        @return list: a list of deleted waveform names.
        """
        return list()

    def delete_sequence(self, sequence_name):
        """ Delete the sequence with name "sequence_name" from the device memory.

        @param str sequence_name: The name of the sequence to be deleted
                                  Optionally a list of sequence names can be passed.

        @return list: a list of deleted sequence names.
        """
        return list()

    def get_interleave(self):
        """ Check whether Interleave is ON or OFF in AWG.

        @return bool: True: ON, False: OFF

        Will always return False for pulse generator hardware without interleave.
        """
        return False

    def set_interleave(self, state=False):
        """ Turns the interleave of an AWG on or off.

        @param bool state: The state the interleave should be set to
                           (True: ON, False: OFF)

        @return bool: actual interleave status (True: ON, False: OFF)

        Note: After setting the interleave of the device, retrieve the
              interleave again and use that information for further processing.

        Unused for pulse generator hardware other than an AWG.
        """
        if state:
            self.log.error('No interleave functionality available in Narwhal pulser.\n'
                           'Interleave state is always False.')
        return False

    
    def reset(self):
        """ Reset the device.

        @return int: error code (0:OK, -1:error)
        """

        self.pulse_streamer.reset()
        self.__currently_loaded_waveform = ''

    
    def has_sequence_mode(self):
        """ Asks the pulse generator whether sequence mode exists.

        @return: bool, True for yes, False for no.
        """
        return False