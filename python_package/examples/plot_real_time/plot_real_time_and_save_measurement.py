import argparse
import logging

import pyqtgraph as pg
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes, WindowOperations, DetrendOperations
from pyqtgraph.Qt import QtGui, QtCore

import serial
from threading import Thread
import pyedflib
import numpy as np
from pyedflib import highlevel
import datetime
import struct


class Graph:
    def __init__(self, board_shim, comport="/dev/ttyUSB0"):

        # MYCODE
        self.id = None
        self.header = None
        self.edf_filename = None
        # self.signals = None
        self.signal_headers = None
        self.data = None
        self.recording_minutes = None
        self.channel_num = None
        self.sampling_rate = None
        self.points_length = None
        self.counter = 0
        self.measurement_ongoing = False

        self.new_measurement(patientname=patientname,
                             recording_minutes=recording_minutes,
                             )
        # END MYCODE

        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self.board_id = board_shim.get_board_id()
        self.board_shim = board_shim
        self.eeg_channels = BoardShim.get_eeg_channels(self.board_id)
        self.sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        # self.update_speed_ms = 50
        self.update_speed_ms = 500
        self.window_size = 4
        self.num_points = self.window_size * self.sampling_rate

        self.app = QtGui.QApplication([])
        self.win = pg.GraphicsWindow(title='BrainFlow Plot', size=(800, 600))

        self._init_pens()
        self._init_timeseries()
        self._init_psd()
        self._init_band_plot()

        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        timer.start(self.update_speed_ms)
        QtGui.QApplication.instance().exec_()

    def _init_pens(self):
        self.pens = list()
        self.brushes = list()
        colors = ['#A54E4E', '#A473B6', '#5B45A4', '#2079D2', '#32B798', '#2FA537', '#9DA52F', '#A57E2F', '#A53B2F']
        for i in range(len(colors)):
            pen = pg.mkPen({'color': colors[i], 'width': 2})
            self.pens.append(pen)
            brush = pg.mkBrush(colors[i])
            self.brushes.append(brush)

    def _init_timeseries(self):
        self.plots = list()
        self.curves = list()
        for i in range(len(self.eeg_channels)):
            p = self.win.addPlot(row=i, col=0)
            p.showAxis('left', False)
            p.setMenuEnabled('left', False)
            p.showAxis('bottom', False)
            p.setMenuEnabled('bottom', False)
            if i == 0:
                p.setTitle('TimeSeries Plot')
            self.plots.append(p)
            curve = p.plot(pen=self.pens[i % len(self.pens)])
            # curve.setDownsampling(auto=True, method='mean', ds=3)
            self.curves.append(curve)

    def _init_psd(self):
        self.psd_plot = self.win.addPlot(row=0, col=1, rowspan=len(self.eeg_channels) // 2)
        self.psd_plot.showAxis('left', False)
        self.psd_plot.setMenuEnabled('left', False)
        self.psd_plot.setTitle('PSD Plot')
        self.psd_plot.setLogMode(False, True)
        self.psd_curves = list()
        self.psd_size = DataFilter.get_nearest_power_of_two(self.sampling_rate)
        for i in range(len(self.eeg_channels)):
            psd_curve = self.psd_plot.plot(pen=self.pens[i % len(self.pens)])
            psd_curve.setDownsampling(auto=True, method='mean', ds=3)
            self.psd_curves.append(psd_curve)

    def _init_band_plot(self):
        self.band_plot = self.win.addPlot(row=len(self.eeg_channels) // 2, col=1, rowspan=len(self.eeg_channels) // 2)
        self.band_plot.showAxis('left', False)
        self.band_plot.setMenuEnabled('left', False)
        self.band_plot.showAxis('bottom', False)
        self.band_plot.setMenuEnabled('bottom', False)
        self.band_plot.setTitle('BandPower Plot')
        y = [0, 0, 0, 0, 0]
        x = [1, 2, 3, 4, 5]
        self.band_bar = pg.BarGraphItem(x=x, height=y, width=0.8, pen=self.pens[0], brush=self.brushes[0])
        self.band_plot.addItem(self.band_bar)

    def update(self):
        data = self.board_shim.get_current_board_data(self.num_points)
        avg_bands = [0, 0, 0, 0, 0]

        for count, channel in enumerate(self.eeg_channels):
            # plot timeseries
            # print(f"data: {data[channel][0]}")
            # self.data[channel - 1][self.counter] = data[channel][0]
            DataFilter.detrend(data[channel], DetrendOperations.CONSTANT.value)
            DataFilter.perform_bandpass(data[channel], self.sampling_rate, 3.0, 45.0, 2,
                                        FilterTypes.BUTTERWORTH.value, 0)
            DataFilter.perform_bandstop(data[channel], self.sampling_rate, 48.0, 52.0, 2,
                                        FilterTypes.BUTTERWORTH.value, 0)
            DataFilter.perform_bandstop(data[channel], self.sampling_rate, 58.0, 62.0, 2,
                                        FilterTypes.BUTTERWORTH.value, 0)
            self.curves[count].setData(data[channel].tolist())
            if data.shape[1] > self.psd_size:
                # plot psd
                psd_data = DataFilter.get_psd_welch(data[channel], self.psd_size, self.psd_size // 2,
                                                    self.sampling_rate,
                                                    WindowOperations.BLACKMAN_HARRIS.value)
                lim = min(70, len(psd_data[0]))
                self.psd_curves[count].setData(psd_data[1][0:lim].tolist(), psd_data[0][0:lim].tolist())
                # plot bands
                avg_bands[0] = avg_bands[0] + DataFilter.get_band_power(psd_data, 2.0, 4.0)
                avg_bands[1] = avg_bands[1] + DataFilter.get_band_power(psd_data, 4.0, 8.0)
                avg_bands[2] = avg_bands[2] + DataFilter.get_band_power(psd_data, 8.0, 13.0)
                avg_bands[3] = avg_bands[3] + DataFilter.get_band_power(psd_data, 13.0, 30.0)
                avg_bands[4] = avg_bands[4] + DataFilter.get_band_power(psd_data, 30.0, 50.0)

        avg_bands = [int(x * 100 / len(self.eeg_channels)) for x in avg_bands]

        if self.measurement_ongoing:
            self.counter += 1
            if self.counter >= self.points_length:
                self.counter = 0
                self.save_file()
                self.measurement_ongoing = False

        self.band_bar.setOpts(height=avg_bands)

        self.app.processEvents()

    def new_measurement(self, patientname, recording_minutes=1, technician="", recording_additional="",
                        patient_additional="", patientcode="", equipment="Geenie", sex="",
                        startdate=datetime.datetime.now(), birthdate="", sampling_rate=250, number_of_channels=8,
                        channel_names=None,
                        edf_filename=datetime.datetime.now().strftime("%d_%m_%Y__%H_%M_%S.edf")):
        self.channel_num = number_of_channels
        self.recording_minutes = recording_minutes
        self.edf_filename = edf_filename
        self.sampling_rate = sampling_rate
        # self.points_length = sampling_rate * 60 * recording_minutes
        self.points_length = 60 * recording_minutes * 2

        if channel_names is None:
            channel_names = []
            for n in range(1, number_of_channels + 1):
                channel_names.append(f"ch{n}")

        # signals = np.random.rand(number_of_channels,
        #                          sampling_rate * 60 * recording_minutes) * 200  # 5 minutes of random signal
        self.data = np.zeros([self.channel_num, self.points_length])

        self.signal_headers = highlevel.make_signal_headers(channel_names,
                                                            sample_frequency=sampling_rate,
                                                            physical_min=-300000,
                                                            physical_max=300000)
        self.header = highlevel.make_header(technician=technician,
                                            recording_additional=recording_additional,
                                            patientname=patientname,
                                            patient_additional=patient_additional,
                                            patientcode=patientcode,
                                            equipment=equipment,
                                            sex=sex,
                                            startdate=startdate,
                                            birthdate=birthdate
                                            )

        print("\n")
        print("New measurement starting:")
        print(f"\tPatient Name: {patientname}")
        print(f"\tBirth Date{birthdate}")
        print("\n")
        print(f"\tDevice: {equipment}")
        print(f"\tNumber of Channels: {number_of_channels}")
        print(f"\tSampling Rate: {sampling_rate}")
        print(f"\tStart Date: {startdate}")
        print(f"\tTechnician: {technician}")
        print("\n")
        print(f"\tDuration: {recording_minutes} minutes")
        print(f"\tFile name: {edf_filename} ")
        print("\n")
        self.measurement_ongoing = True


    def save_file(self):
        mydata = self.board_shim.get_current_board_data(250 * recording_minutes * 60)

        for count, channel in enumerate(self.eeg_channels):
            # plot timeseries
            # print(f"data: {data[channel][0]}")
            self.data[channel - 1][self.counter] = mydata[channel][0]
            DataFilter.detrend(mydata[channel], DetrendOperations.CONSTANT.value)
            DataFilter.perform_bandpass(mydata[channel], self.sampling_rate, 3.0, 45.0, 2,
                                        FilterTypes.BUTTERWORTH.value, 0)
            DataFilter.perform_bandstop(mydata[channel], self.sampling_rate, 48.0, 52.0, 2,
                                        FilterTypes.BUTTERWORTH.value, 0)
            # DataFilter.perform_bandstop(mydata[channel], self.sampling_rate, 58.0, 62.0, 2,
            #                             FilterTypes.BUTTERWORTH.value, 0)
            self.curves[count].setData(mydata[channel].tolist())

        mydata = mydata[1:self.channel_num+1]

        # print(mydata)
        # print(len(self.signal_headers))
        # print(len(mydata))
        highlevel.write_edf(edf_file=self.edf_filename,
                            signals=mydata,
                            signal_headers=self.signal_headers,
                            header=self.header)
        print("File saved")

    def hexlify(self, data):
        return ' '.join(f'{c:0>2X}' for c in data)

    def read(self):
        counter = 0

        temp = False
        mylist = []
        mylistint = []

        while counter < self.points_length:
            x = self.ser.read()
            byt = self.hexlify(x)
            if temp:
                if byt == "41":
                    print(x)
                    temp = True
                    # print(byt)
                    mylist.append(byt)
                    mylistint.append(x)
            else:
                mylist.append(byt)
                mylistint.append(x)
                if byt == "C0":
                    if len(mylist) > 30:
                        print(mylist)
                        for ch in range(self.channel_num):
                            # TODO Conversion here is probably wrong, check brainflow's conversin process
                            channel_byte_array = mylistint[(2 + ch * 3):(2 + ch * 3 + 3)]
                            channel_byte_array.append(b'?')
                            bstr = b''.join(channel_byte_array)
                            channel_float_value = struct.unpack('f', bstr)[0]
                            self.data[ch][counter] = channel_float_value
                        counter += 1
                        mylist = []
                        mylistint = []
                        temp = False
        self.measurement_ongoing = False
        self.save_file()
        return None


if __name__ == '__main__':

    comport = "COM5"
    patientname = "Patient1"
    recording_minutes = 10

    BoardShim.enable_dev_board_logger()
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    # use docs to check which parameters are required for specific board, e.g. for Cyton - set serial port
    parser.add_argument('--timeout', type=int, help='timeout for device discovery or connection', required=False,
                        default=0)
    parser.add_argument('--ip-port', type=int, help='ip port', required=False, default=0)
    parser.add_argument('--ip-protocol', type=int, help='ip protocol, check IpProtocolType enum', required=False,
                        default=0)
    parser.add_argument('--ip-address', type=str, help='ip address', required=False, default='')
    # parser.add_argument('--serial-port', type=str, help='serial port', required=False, default='/dev/ttyUSB1')
    parser.add_argument('--serial-port', type=str, help='serial port', required=False, default='COM4')
    parser.add_argument('--mac-address', type=str, help='mac address', required=False, default='')
    parser.add_argument('--other-info', type=str, help='other info', required=False, default='')
    parser.add_argument('--streamer-params', type=str, help='streamer params', required=False, default='')
    parser.add_argument('--serial-number', type=str, help='serial number', required=False, default='')
    parser.add_argument('--board-id', type=int, help='board id, check docs to get a list of supported boards',
                        required=False, default=BoardIds.SYNTHETIC_BOARD)
    parser.add_argument('--file', type=str, help='file', required=False, default='')
    parser.add_argument('--master-board', type=int, help='master board id for streaming and playback boards',
                        required=False, default=BoardIds.NO_BOARD)
    args = parser.parse_args()

    params = BrainFlowInputParams()
    params.ip_port = args.ip_port
    params.serial_port = comport
    params.mac_address = args.mac_address
    params.other_info = args.other_info
    params.serial_number = args.serial_number
    params.ip_address = args.ip_address
    params.ip_protocol = args.ip_protocol
    params.timeout = args.timeout
    params.file = args.file
    params.master_board = args.master_board

    # board_shim = BoardShim(args.board_id, params)
    board_shim = BoardShim(49, params)
    try:
        board_shim.prepare_session()
        board_shim.start_stream(450000, args.streamer_params)
        Graph(board_shim, comport)

    except BaseException:
        logging.warning('Exception', exc_info=True)
    finally:
        if board_shim.is_prepared():
            logging.info('Releasing session')
            board_shim.release_session()