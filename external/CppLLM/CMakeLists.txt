cmake_minimum_required(VERSION 3.16)
project(CppLLM)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)

set(PROTO_DIR ${CMAKE_CURRENT_SOURCE_DIR}/proto)
set(PROTO_FILE ${PROTO_DIR}/llm_service.proto)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)

file(MAKE_DIRECTORY ${GENERATED_DIR})

set(PROTO_SRCS ${GENERATED_DIR}/llm_service.pb.cc)
set(PROTO_HDRS ${GENERATED_DIR}/llm_service.pb.h)
set(GRPC_SRCS ${GENERATED_DIR}/llm_service.grpc.pb.cc)
set(GRPC_HDRS ${GENERATED_DIR}/llm_service.grpc.pb.h)

add_custom_command(
    OUTPUT ${PROTO_SRCS} ${PROTO_HDRS}
    COMMAND protobuf::protoc
    ARGS --proto_path=${PROTO_DIR}
         --cpp_out=${GENERATED_DIR}
         ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
)

add_custom_command(
    OUTPUT ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND protobuf::protoc
    ARGS --proto_path=${PROTO_DIR}
         --grpc_out=${GENERATED_DIR}
         --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
         ${PROTO_FILE}
    DEPENDS ${PROTO_FILE} ${PROTO_SRCS} ${PROTO_HDRS}
)

add_library(llm_proto STATIC
    ${PROTO_SRCS}
    ${GRPC_SRCS}
)

target_link_libraries(llm_proto
    PUBLIC
    protobuf::libprotobuf
    gRPC::grpc++
)

target_include_directories(llm_proto
    PUBLIC
    ${GENERATED_DIR}
)

set(SRC
    src/main.cpp
    src/llm_engine.cpp
    src/grpc_server.mm
    src/mcp_adapter.cpp
    src/apple_api/eventkit.mm
)

add_executable(CppLLM ${SRC})

target_include_directories(CppLLM
    PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${GENERATED_DIR}
)

target_link_libraries(CppLLM
    PRIVATE
    llm_proto
    gRPC::grpc++_reflection
)

add_dependencies(CppLLM llm_proto)

if(APPLE)
    find_library(FOUNDATION_FRAMEWORK Foundation)
    find_library(EVENTKIT_FRAMEWORK EventKit)
    if(FOUNDATION_FRAMEWORK AND EVENTKIT_FRAMEWORK)
        target_link_libraries(CppLLM PRIVATE ${FOUNDATION_FRAMEWORK} ${EVENTKIT_FRAMEWORK})
    endif()
endif()

set_source_files_properties(
    src/apple_api/eventkit.mm
    src/grpc_server.mm
    PROPERTIES LANGUAGE OBJCXX)
