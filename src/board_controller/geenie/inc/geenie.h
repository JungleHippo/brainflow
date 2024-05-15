#pragma once

#include <math.h>
#include <string>

#include "geenie_gain_tracker.h"
#include "geenie_serial_board.h"

class Geenie : public GeenieSerialBoard
{
protected:
    GeenieGainTracker gain_tracker;

    void read_thread ();

public:
    Geenie (struct BrainFlowInputParams params)
        : GeenieSerialBoard (params, (int)BoardIds::GEENIE_BOARD)
    {
    }

    int config_board (std::string config, std::string &response);
};