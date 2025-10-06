#pragma once

#include <string>

struct EventCreationResult {
    bool success;
    std::string message;
    std::string event_identifier;
};

EventCreationResult createCalendarEvent(const std::string& person,
                                        const std::string& isoStartTime,
                                        int durationMinutes);
