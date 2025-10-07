#pragma once
#include <string>

class LLMEngine {
public:
    void initialize();
    std::string runInference(const std::string& input);
};
