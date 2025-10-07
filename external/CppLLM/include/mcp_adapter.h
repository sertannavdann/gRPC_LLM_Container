#pragma once
#include <string>

class MCPAdapter {
public:
    std::string extractIntent(const std::string& llmOutput);
};
