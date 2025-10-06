// Entry point for CppLLM
#include "../include/llm_engine.h"
#include "../include/grpc_server.h"

#include <cstdlib>
#include <iostream>
#include <string>

int main(int argc, char* argv[]) {
    // Initialize LLM Engine
    LLMEngine engine;
    engine.initialize();

    // Start gRPC server
    std::string bindAddress = "0.0.0.0:50061";
    if (const char* envAddr = std::getenv("CPP_LLM_BIND_ADDR")) {
        bindAddress = envAddr;
    }
    if (argc > 1) {
        bindAddress = argv[1];
    }

    std::cout << "[cpp-llm] Starting server with bind address: " << bindAddress << std::endl;
    GRPCServer server(&engine, bindAddress);
    server.run();

    return 0;
}
