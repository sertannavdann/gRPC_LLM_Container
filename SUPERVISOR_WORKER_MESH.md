# Supervisor-Worker Mesh Architecture

This document describes the new Supervisor-Worker architecture with Dynamic Registry.

## Overview

The system has been evolved to support a mesh of specialized agents coordinated by a Supervisor.

### Components

1.  **Supervisor (Orchestrator)**:
    -   The main entry point.
    -   Holds conversation state.
    -   Uses a smart model (LLM) to decide when to delegate tasks.
    -   Discovers workers via the Registry.

2.  **Registry Service**:
    -   A lightweight gRPC service.
    -   Agents register their capabilities here.
    -   Supervisor queries this to find "Who can do X?".

3.  **Worker Nodes**:
    -   Specialized agents (e.g., Coding Agent).
    -   Register with the Registry on startup.
    -   Execute tasks sent by the Supervisor.

## Usage

### 1. Start the Stack

```bash
make build
make up
```

This will start:
-   `orchestrator` (Supervisor)
-   `registry_service`
-   `worker_coding` (A sample worker with "coding" capability)
-   `llm_service` & `chroma_service` (Support services)
-   `ui_service`

### 2. Delegation Flow

1.  User asks a question (e.g., "Write a Python script to...").
2.  Orchestrator's LLM decides to use the `delegate_to_worker` tool.
3.  `delegate_to_worker` calls `RegistryClient.discover("coding")`.
4.  Registry returns the endpoint of `worker_coding`.
5.  Orchestrator calls `WorkerClient.execute_task(...)` on the worker.
6.  Worker executes the task and returns the result.
7.  Orchestrator incorporates the result into the final response.

## Extending

To add a new worker type:
1.  Create a new worker service (copy `worker_service`).
2.  Update `WORKER_CAPABILITIES` env var.
3.  Add to `docker-compose.yaml`.

## Protobufs

-   `shared/proto/registry.proto`: Registry service definition.
-   `shared/proto/worker.proto`: Worker service definition.
