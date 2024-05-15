import argparse
import time

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowPresets


def main():
    BoardShim.enable_dev_board_logger()

    params = BrainFlowInputParams()
    params.ip_port = 0
    params.serial_port = "COM4"
    params.mac_address = ''
    params.other_info = ''
    params.serial_number = ''
    params.ip_address = ''
    params.ip_protocol = 0
    params.timeout = 0
    params.file = ''
    params.master_board = BoardIds.NO_BOARD

    board = BoardShim(BoardIds.EGEENIE_BOARD, params)
    board.prepare_session()
    board.start_stream()
    time.sleep(5)
    # data = board.get_current_board_data (256) # get latest 256 packages or less, doesnt remove them from internal buffer
    data = board.get_board_data()  # get all data and remove it from internal buffer
    board.stop_stream()
    board.release_session()

    print(data)
    print(len(data[0]))
    print(len(data[1]))


if __name__ == "__main__":
    main()