# CppLLM

CppLLM is a lightweight C++ foundation for running large language models locally with Metal acceleration and exposing them through gRPC so Apple App Intents and Siri shortcuts can orchestrate native workflows.

## Features

- Minimal LLM engine stub with hooks for integrating llama.cpp (Metal backend).
- Production-ready gRPC surface (`cpp_llm.CppLLMService`) with structured logging and health reflection.
- MCP adapter layer for turning LLM output into actionable intents.
- Apple API adapters (Objective-C++) ready to call frameworks like EventKit.

## Repository Layout

```
CppLLM/
├── CMakeLists.txt         # Build configuration
├── proto/                 # gRPC contracts
│   └── llm_service.proto
├── include/               # Public headers
│   ├── eventkit.h
│   ├── grpc_server.h
│   ├── llm_engine.h
│   └── mcp_adapter.h
└── src/
    ├── apple_api/
    │   └── eventkit.mm    # Objective-C++ adapter stub
    ├── grpc_server.cpp
    ├── llm_engine.cpp
    ├── main.cpp
    └── mcp_adapter.cpp
```

## Getting Started

1. Install prerequisites (macOS with Xcode tools, CMake, Protobuf, gRPC, llama.cpp dependencies).
2. Configure and build:

```sh
mkdir build && cd build
cmake ..
make
```

3. Extend the stubs:
    - Implement Metal-backed llama.cpp initialization inside `llm_engine.cpp`.
    - Swap the uppercase placeholder in `llm_engine.cpp` with true model inference.
    - Expand the `MCPAdapter` intent payload if you surface additional structured outputs.
    - Add more Apple adapters in `src/apple_api/` as needed.

### Running the gRPC service locally

Build and run directly on macOS (the server binds to `0.0.0.0:50061` by default):

```sh
mkdir -p build && cd build
cmake ..
cmake --build .
./CppLLM
```

Override the bind address via CLI or environment variable:

```sh
CPP_LLM_BIND_ADDR="127.0.0.1:51000" ./CppLLM
# or
./CppLLM 127.0.0.1:51000
```

Once the server is running you can query it with the generated gRPC stubs:

```sh
grpcurl -plaintext -d '{"input":"Schedule a call with Sarah tomorrow 2pm"}' localhost:50061 cpp_llm.CppLLMService/RunInference
```

The response includes both the raw inference output and a structured `intent_payload` usable by the orchestrator.

### Sprint 1 (current)

- ✅ Introduced `AppIntentsPackage`, a shared Swift package that centralizes App Intent definitions.
- ✅ Added `ScheduleMeetingIntent` placeholder plus unit tests (`swift test`).
- ✅ Published `AppIntentCatalog` helpers to expose intent groupings to both the host app and Intents extension.

Add the package to Xcode via **File ▸ Add Packages…**, selecting `external/CppLLM/AppIntentsPackage`. The Objective-C++ adapters will call into these intents during Sprint 2 when the gRPC handlers are extended.

## Next Steps

- Add additional Apple adapters (Apple Pay, Contacts, Reminders, PhotoKit).
- Generate gRPC bindings from `proto/llm_service.proto`.
- Wire the service into the `gRPC_LLM_Container` project by replacing its LLM service implementation.

This scaffold keeps the surface area minimal so you can focus on plugging in existing components instead of rewriting them from scratch.
