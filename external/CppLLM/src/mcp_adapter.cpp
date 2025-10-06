// MCP Adapter implementation
#include "../include/mcp_adapter.h"

#include <algorithm>
#include <optional>
#include <regex>
#include <sstream>
#include <string>

namespace {
std::string makeLowerCopy(const std::string& text) {
    std::string lowered{text};
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return lowered;
}

std::optional<std::string> extractPerson(const std::string& text) {
    std::regex withRegex{"with\\s+([A-Za-z]+)"};
    std::smatch match;
    if (std::regex_search(text, match, withRegex) && match.size() > 1) {
        return match[1];
    }
    return std::nullopt;
}

std::optional<std::string> extractDatePhrase(const std::string& text) {
    std::regex dateRegex{"(next\\s+[a-zA-Z]+|tomorrow|today|[a-zA-Z]+\\s+\\d{1,2})"};
    std::smatch match;
    if (std::regex_search(text, match, dateRegex) && match.size() > 1) {
        return match[1];
    }
    return std::nullopt;
}

std::optional<std::string> extractTime(const std::string& text) {
    std::regex timeRegex{"(\\d{1,2}(?::\\d{2})?\\s?(am|pm)?)"};
    std::smatch match;
    if (std::regex_search(text, match, timeRegex) && match.size() > 1) {
        return match[1];
    }
    return std::nullopt;
}
}

std::string MCPAdapter::extractIntent(const std::string& llmOutput) {
    const std::string lowered = makeLowerCopy(llmOutput);

    std::ostringstream payload;
    payload << "{\n";

    if (lowered.find("schedule") != std::string::npos || lowered.find("meeting") != std::string::npos) {
        payload << "  \"intent\": \"schedule_event\",\n";
    } else if (lowered.find("spend") != std::string::npos && lowered.find("grocer") != std::string::npos) {
        payload << "  \"intent\": \"financial_summary\",\n";
    } else {
        payload << "  \"intent\": \"generic_query\",\n";
    }

    auto person = extractPerson(lowered);
    if (person) {
        payload << "  \"person\": \"" << *person << "\",\n";
    }

    auto datePhrase = extractDatePhrase(lowered);
    if (datePhrase) {
        payload << "  \"datetime_hint\": \"" << *datePhrase << "\",\n";
    }

    auto timePhrase = extractTime(lowered);
    if (timePhrase) {
        payload << "  \"time_hint\": \"" << *timePhrase << "\",\n";
    }

    payload << "  \"raw\": \"";
    for (char c : llmOutput) {
        if (c == '"') {
            payload << "\\\"";
        } else if (c == '\n') {
            payload << "\\n";
        } else {
            payload << c;
        }
    }
    payload << "\"\n";
    payload << "}";

    return payload.str();
}
