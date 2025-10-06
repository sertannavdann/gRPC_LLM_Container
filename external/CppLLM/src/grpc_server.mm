// gRPC server implementation
#include "../include/grpc_server.h"

#include "../include/eventkit_bridge.h"
#include "../include/llm_engine.h"
#include "../include/mcp_adapter.h"

#include "llm_service.grpc.pb.h"

#include <grpcpp/grpcpp.h>
#include <grpcpp/ext/proto_server_reflection_plugin.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

namespace {

class LLMServiceImpl final : public cpp_llm::CppLLMService::Service {
public:
    explicit LLMServiceImpl(LLMEngine* engine) : engine_(engine) {}

    grpc::Status RunInference(grpc::ServerContext* /*context*/,
                              const cpp_llm::InferenceRequest* request,
                              cpp_llm::InferenceResponse* response) override {
        if (engine_ == nullptr) {
            return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION, "LLM engine unavailable");
        }

        const auto& input = request->input();
        std::cout << "[cpp-llm][grpc] request received: " << input << std::endl;

        const std::string llmOutput = engine_->runInference(input);
        response->set_output(llmOutput);
        std::cout << "[cpp-llm][grpc] inference output: " << llmOutput << std::endl;

        MCPAdapter adapter;
        const std::string intent = adapter.extractIntent(llmOutput.empty() ? input : llmOutput);
        response->set_intent_payload(intent);
        std::cout << "[cpp-llm][grpc] intent payload: " << intent << std::endl;

        return grpc::Status::OK;
    }

    grpc::Status TriggerScheduleMeeting(grpc::ServerContext* /*context*/,
                                        const cpp_llm::ScheduleMeetingRequest* request,
                                        cpp_llm::ScheduleMeetingResponse* response) override {
        std::cout << "[cpp-llm][grpc] schedule request - person: " << request->person()
                  << ", start: " << request->start_time_iso8601()
                  << ", duration: " << request->duration_minutes() << std::endl;

        EventCreationResult result = createCalendarEvent(
            request->person(),
            request->start_time_iso8601(),
            request->duration_minutes());

        response->set_message(result.message);
        response->set_event_identifier(result.event_identifier);
        if (result.success) {
            response->set_status(cpp_llm::ScheduleMeetingResponse::STATUS_OK);
            std::cout << "[cpp-llm][grpc] event scheduled with id: " << result.event_identifier << std::endl;
            return grpc::Status::OK;
        }

        response->set_status(cpp_llm::ScheduleMeetingResponse::STATUS_ERROR);
        std::cerr << "[cpp-llm][grpc] failed to schedule event: " << result.message << std::endl;
        const std::string errorMessage = result.message.empty() ? "Event scheduling failed" : result.message;
        return grpc::Status(grpc::StatusCode::INTERNAL, errorMessage);
    }

private:
    LLMEngine* engine_;
};

std::atomic_bool g_shutdownRequested{false};

void handleSignal(int /*signal*/) {
    g_shutdownRequested = true;
}

} // namespace

GRPCServer::GRPCServer(LLMEngine* engine, std::string address)
    : engine_(engine), address_(std::move(address)) {}

void GRPCServer::run() {
    if (engine_ == nullptr) {
        std::cerr << "[cpp-llm][grpc] No engine provided, aborting server start." << std::endl;
        return;
    }

    std::signal(SIGINT, handleSignal);
    std::signal(SIGTERM, handleSignal);

    LLMServiceImpl service(engine_);

    grpc::EnableDefaultHealthCheckService(true);
    grpc::reflection::InitProtoReflectionServerBuilderPlugin();

    grpc::ServerBuilder builder;
    builder.AddListeningPort(address_, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);

    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    if (!server) {
        std::cerr << "[cpp-llm][grpc] Failed to start server on " << address_ << std::endl;
        return;
    }

    std::cout << "[cpp-llm][grpc] Server listening on " << address_ << std::endl;

    while (!g_shutdownRequested.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    std::cout << "[cpp-llm][grpc] Shutdown signal received. Initiating graceful stop..." << std::endl;
    server->Shutdown();
    server->Wait();
    std::cout << "[cpp-llm][grpc] Server stopped." << std::endl;
}
