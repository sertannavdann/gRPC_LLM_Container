#pragma once
#include <string>

class LLMEngine;

class GRPCServer {
public:
    GRPCServer(LLMEngine* engine, std::string address = "0.0.0.0:50061");
    void run();

private:
    LLMEngine* engine_;
    std::string address_;
};
