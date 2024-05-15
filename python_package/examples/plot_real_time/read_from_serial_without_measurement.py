import serial
from threading import Thread
import pyedflib
import numpy as np
from pyedflib import highlevel
import datetime
import struct


class Geenie:
    def __init__(self, port):
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
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )
        self.measurement_ongoing = False

    def new_measurement(self, patientname, recording_minutes=1, technician="", recording_additional="",
                        patient_additional="", patientcode="", equipment="Geenie", sex="",
                        startdate=datetime.datetime.now(), birthdate="", sampling_rate=250, number_of_channels=8,
                        channel_names=None,
                        edf_filename=datetime.datetime.now().strftime("%d_%m_%Y__%H_%M_%S.edf")):
        self.channel_num = number_of_channels
        self.recording_minutes = recording_minutes
        self.edf_filename = edf_filename
        self.sampling_rate = sampling_rate
        self.points_length = sampling_rate * 60 * recording_minutes

        if channel_names is None:
            channel_names = []
            for n in range(1, number_of_channels + 1):
                channel_names.append(f"ch{n}")

        # signals = np.random.rand(number_of_channels,
        #                          sampling_rate * 60 * recording_minutes) * 200  # 5 minutes of random signal
        self.data = np.zeros([self.channel_num, self.points_length])

        self.signal_headers = highlevel.make_signal_headers(channel_names, sample_frequency=sampling_rate)
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

    def start_measurement(self):
        self.measurement_ongoing = True
        thread = Thread(target=self.read)
        print("Measurement ongoing...")
        thread.start()
        # while self.measurement_ongoing:
        #     comm = input()
        #     self.ser.write(comm.encode())

    def save_file(self):
        highlevel.write_edf(edf_file=self.edf_filename,
                            signals=self.data,
                            signal_headers=self.signal_headers,
                            header=self.header)

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
                            channel_byte_array = mylistint[(2+ch*3):(2+ch*3+3)]
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


if __name__ == "__main__":
    geenie = Geenie(port="COM6")
    geenie.new_measurement(patientname="Vasilis Vasilopoulos",
                           recording_minutes=1,
                           )
    geenie.start_measurement()
    # while True:
    #     pass

    # def read(self):
    #     temp = False
    #     mylist = []
    #
    #     while 1:
    #         x = self.ser.read()
    #         byt = self.hexlify(x)
    #         if temp:
    #             if byt == "41":
    #                 temp = True
    #                 # print(byt)
    #                 mylist.append(byt)
    #         else:
    #             mylist.append(byt)
    #             if byt == "C0":
    #                 if len(mylist) > 30:
    #
    #                     mylist = []
    #                     temp = False

# thread = Thread(target=self.read)
# thread.start()
# while self.measurement_ongoing:
#     comm = input()
#     self.ser.write(comm.encode())
# pass