#include <math.h>
#include <string.h>
#include <vector>

#include "custom_cast.h"
#include "egeenie.h"
#include "serial.h"
#include "timestamp.h"


constexpr int Egeenie::start_byte;
constexpr int Egeenie::end_byte;
constexpr double Egeenie::ads_gain;
constexpr double Egeenie::ads_vref;

#define START_BYTE 0x41
#define END_BYTE_STANDARD 0xC0
#define END_BYTE_MAX 0xC6



Egeenie::Egeenie (struct BrainFlowInputParams params)
    : Board ((int)BoardIds::EGEENIE_BOARD, params)
{
    serial = NULL;
    is_streaming = false;
    keep_alive = false;
    initialized = false;
}

Egeenie::~Egeenie ()
{
    skip_logs = true;
    release_session ();
}

int Egeenie::prepare_session ()
{
    if (initialized)
    {
        safe_logger (spdlog::level::info, "Session already prepared");
        return (int)BrainFlowExitCodes::STATUS_OK;
    }
    if (params.serial_port.empty ())
    {
        safe_logger (spdlog::level::err, "serial port is empty");
        return (int)BrainFlowExitCodes::INVALID_ARGUMENTS_ERROR;
    }
    serial = Serial::create (params.serial_port.c_str (), this);
    int port_open = open_port ();
    if (port_open != (int)BrainFlowExitCodes::STATUS_OK)
    {
        delete serial;
        serial = NULL;
        return port_open;
    }

    int set_settings = set_port_settings ();
    if (set_settings != (int)BrainFlowExitCodes::STATUS_OK)
    {
        delete serial;
        serial = NULL;
        return set_settings;
    }

    initialized = true;
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int Egeenie::start_stream (int buffer_size, const char *streamer_params)
{
    if (is_streaming)
    {
        safe_logger (spdlog::level::err, "Streaming thread already running");
        return (int)BrainFlowExitCodes::STREAM_ALREADY_RUN_ERROR;
    }
    int res = prepare_for_acquisition (buffer_size, streamer_params);
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        return res;
    }

    serial->flush_buffer ();

    keep_alive = true;
    streaming_thread = std::thread ([this] { this->read_thread (); });
    is_streaming = true;
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int Egeenie::stop_stream ()
{
    if (is_streaming)
    {
        keep_alive = false;
        is_streaming = false;
        if (streaming_thread.joinable ())
        {
            streaming_thread.join ();
        }
        return (int)BrainFlowExitCodes::STATUS_OK;
    }
    else
    {
        return (int)BrainFlowExitCodes::STREAM_THREAD_IS_NOT_RUNNING;
    }
}

int Egeenie::release_session ()
{
    if (initialized)
    {
        if (is_streaming)
        {
            stop_stream ();
        }
        free_packages ();
        initialized = false;
    }
    if (serial)
    {
        serial->close_serial_port ();
        delete serial;
        serial = NULL;
    }
    return (int)BrainFlowExitCodes::STATUS_OK;
}

void Egeenie::read_thread ()
{
    /*
        Byte 1: 0xA0
        Byte 2: Sample Number
        Bytes 3-5: Data value for EEG channel 1
        Bytes 6-8: Data value for EEG channel 2
        Bytes 9-11: Data value for EEG channel 3
        Bytes 12-14: Data value for EEG channel 4
        Bytes 15-17: Data value for EEG channel 5
        Bytes 18-20: Data value for EEG channel 6
        Bytes 21-23: Data value for EEG channel 6
        Bytes 24-26: Data value for EEG channel 8
        Aux Data Bytes 27-32: 6 bytes of data
        Byte 33: 0xCX where X is 0-F in hex
    */
    int res;
    // unsigned char b[32];
    unsigned char b[30];
    // double accel[3] = {0.};
    int num_rows = board_descr["default"]["num_rows"];
    double *package = new double[num_rows];
    for (int i = 0; i < num_rows; i++)
    {
        package[i] = 0.0;
    }
    std::vector<int> eeg_channels = board_descr["default"]["eeg_channels"];
    // double accel_scale = (double)(0.002 / (pow (2, 4)));

    while (keep_alive)
    {
        // check start byte
        res = serial->read_from_serial_port (b, 1);
        if (res != 1)
        {
            safe_logger (spdlog::level::debug, "unable to read 1 byte");
            continue;
        }
        if (b[0] != START_BYTE)
        {
            
            continue;
        }
        // int remaining_bytes = 32;
        int remaining_bytes = 30;
        int pos = 0;
        while ((remaining_bytes > 0) && (keep_alive))
        {
            res = serial->read_from_serial_port (b + pos, remaining_bytes);
            remaining_bytes -= res;
            pos += res;
        }
        if (!keep_alive)
        {
            break;
        }

        if ((b[29] < END_BYTE_STANDARD) || (b[29] > END_BYTE_MAX))
        {
            safe_logger (spdlog::level::warn, "Wrong end byte {}", b[29]);
            continue;
        }

        // package num
        package[board_descr["default"]["package_num_channel"].get<int> ()] = (double)b[0];
        // eeg
        for (unsigned int i = 0; i < eeg_channels.size (); i++)
        {
            double eeg_scale = (double)(4.5 / float ((pow (2, 23) - 1)) /
                gain_tracker.get_gain_for_channel (i) * 1000000.);
            package[eeg_channels[i]] = eeg_scale * cast_24bit_to_int32 (b + 1 + 3 * i);
        }
        // end byte
        // package[board_descr["default"]["other_channels"][0].get<int> ()] = (double)b[31];
        // package[board_descr["default"]["other_channels"][0].get<int> ()] = (double)b[27];
        // place unprocessed bytes for all modes to other_channels
        // package[board_descr["default"]["other_channels"][1].get<int> ()] = (double)b[25];
        // package[board_descr["default"]["other_channels"][2].get<int> ()] = (double)b[26];
        // package[board_descr["default"]["other_channels"][3].get<int> ()] = (double)b[27];
        // package[board_descr["default"]["other_channels"][4].get<int> ()] = (double)b[28];
        // package[board_descr["default"]["other_channels"][5].get<int> ()] = (double)b[29];
        // package[board_descr["default"]["other_channels"][6].get<int> ()] = (double)b[30];
        // package[board_descr["default"]["other_channels"][1].get<int> ()] = (double)b[25];
        // package[board_descr["default"]["other_channels"][2].get<int> ()] = (double)b[26];
        // package[board_descr["default"]["other_channels"][3].get<int> ()] = (double)b[27];
        // package[board_descr["default"]["other_channels"][4].get<int> ()] = (double)b[28];
        // package[board_descr["default"]["other_channels"][5].get<int> ()] = (double)b[29];
        // package[board_descr["default"]["other_channels"][6].get<int> ()] = (double)b[30];
        // place processed bytes for accel
        // if (b[31] == END_BYTE_STANDARD)
        // {
        //     int32_t accel_temp[3] = {0};
        //     accel_temp[0] = cast_16bit_to_int32 (b + 25);
        //     accel_temp[1] = cast_16bit_to_int32 (b + 27);
        //     accel_temp[2] = cast_16bit_to_int32 (b + 29);

        //     if (accel_temp[0] != 0)
        //     {
        //         accel[0] = accel_scale * accel_temp[0];
        //         accel[1] = accel_scale * accel_temp[1];
        //         accel[2] = accel_scale * accel_temp[2];
        //     }

        //     package[board_descr["default"]["accel_channels"][0].get<int> ()] = accel[0];
        //     package[board_descr["default"]["accel_channels"][1].get<int> ()] = accel[1];
        //     package[board_descr["default"]["accel_channels"][2].get<int> ()] = accel[2];
        // }
        package[board_descr["default"]["timestamp_channel"].get<int> ()] = get_timestamp ();

        push_package (package);
    }
    delete[] package;
}

int Egeenie::open_port ()
{
    if (serial->is_port_open ())
    {
        safe_logger (spdlog::level::err, "port {} already open", serial->get_port_name ());
        return (int)BrainFlowExitCodes::PORT_ALREADY_OPEN_ERROR;
    }

    safe_logger (spdlog::level::info, "openning port {}", serial->get_port_name ());
    int res = serial->open_serial_port ();
    if (res < 0)
    {
        return (int)BrainFlowExitCodes::UNABLE_TO_OPEN_PORT_ERROR;
    }
    safe_logger (spdlog::level::trace, "port {} is open", serial->get_port_name ());
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int Egeenie::set_port_settings ()
{
    int res = serial->set_serial_port_settings (1000, false);
    if (res < 0)
    {
        safe_logger (spdlog::level::err, "Unable to set port settings, res is {}", res);
#ifndef _WIN32
        return (int)BrainFlowExitCodes::SET_PORT_ERROR;
#endif
    }
    // res = serial->set_custom_baudrate (115200);
    // if (res < 0)
    // {
        // safe_logger (spdlog::level::err, "Unable to set custom baud rate, res is {}", res);
// #ifndef _WIN32
        // Setting the baudrate may return an error on Windows for some serial drivers.
        // We do not throw an exception, because it will still work with USB.
        // Optical connection will fail, though.
        // return (int)BrainFlowExitCodes::SET_PORT_ERROR;
// #endif
    // }
    safe_logger (spdlog::level::trace, "set port settings");
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int Egeenie::config_board (std::string config, std::string &response)
{
    safe_logger (spdlog::level::err, "FreeEEG32 doesn't support board configuration.");
    return (int)BrainFlowExitCodes::UNSUPPORTED_BOARD_ERROR;
}