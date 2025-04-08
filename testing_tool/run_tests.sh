#!/bin/bash

# Set absolute path to project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="${PROJECT_ROOT}/shared/proto:${PYTHONPATH}"

# Start fresh
docker-compose down

# Generate protobuf stubs
echo "Generating protobuf stubs..."
python -m grpc_tools.protoc -I shared/proto \
    --python_out=. \
    --grpc_python_out=. \
    --proto_path=. \
    shared/proto/*.proto
    
# Run services and tests
docker-compose up -d
sleep 15  # Wait for services to initialize

echo "Running unit tests..."
pytest "${PROJECT_ROOT}/testing_tool/tests/test_unit.py" -v

echo "Running integration tests..."
pytest "${PROJECT_ROOT}/testing_tool/tests/test_integration.py" -v

echo "Running E2E test..."
pytest "${PROJECT_ROOT}/testing_tool/tests/test_e2e.py" -v

# Cleanup
docker-compose down