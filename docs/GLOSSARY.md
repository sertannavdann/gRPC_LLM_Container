# Glossary

Definitions of terms, concepts, and abbreviations used in NEXUS.

---

## A

**Adapter**
: Python class that fetches data from external sources and transforms it to canonical schemas. Extends `BaseAdapter[T]`.

**AdapterResult**
: Generic dataclass containing transformed data, metadata, and errors from an adapter.

**Admin API**
: REST API (port 8003) for module management, credential storage, and configuration hot-reload.

---

## C

**Canonical Schema**
: Pydantic model in `shared/schemas/canonical.py` that defines the standard shape for domain-specific data (e.g., `FinancialTransaction`, `WeatherData`).

**Category**
: Broad classification of adapters (e.g., "weather", "finance", "gaming"). Can be predefined (`AdapterCategory` enum) or custom (string).

**cAdvisor**
: Container Advisor - Google's tool for monitoring container resource usage (CPU, memory, network).

**ChromaDB**
: Vector database used for RAG (Retrieval-Augmented Generation) via gRPC service on port 50052.

**Context Bridge**
: HTTP-based communication pattern between orchestrator and dashboard services. Replaces direct Python imports to decouple services.

**Credential Store**
: SQLite database (`data/module_credentials.db`) with Fernet-encrypted credentials for adapters.

---

## D

**Dashboard Service**
: FastAPI service (port 8001) that aggregates context from adapters and exposes REST endpoints.

**Delegation Manager**
: Component in orchestrator that classifies task complexity for LIDM routing.

---

## F

**Fernet**
: Symmetric encryption method (from cryptography.io) used for credential storage. Includes authentication (HMAC) and timestamp-based expiration.

---

## G

**Grafana**
: Visualization platform (port 3000) for metrics dashboards and alerting.

**gRPC**
: Google Remote Procedure Call - Binary protocol used for inter-service communication (orchestrator, LLM, chroma, sandbox).

---

## L

**LIDM (Language-Integrated Decision Making)**
: Pattern where a small LLM classifies task complexity, then routes to appropriate tier (standard/heavy). Reduces latency and cost for simple queries.

**LLM Service**
: gRPC service (port 50051) that runs llama.cpp for local model inference.

**LLMClientPool**
: Manages connections to LLM models across tiers. Supports hot-swapping endpoints.

---

## M

**Manifest**
: JSON file (`manifest.json`) in module directory defining metadata: name, category, platform, version, adapter_class, required_credentials.

**Module**
: Self-contained package in `modules/{category}/{platform}/` with manifest, adapter, and tests. Dynamically loaded at runtime.

**Module Loader**
: Component that uses `importlib.util.spec_from_file_location()` to dynamically import adapters.

**Module Registry**
: SQLite database (`data/module_registry.db`) tracking installed modules with status, enabled_at, disabled_at timestamps.

**ModuleMetrics**
: Dataclass in `shared/observability/metrics.py` tracking module lifecycle events (builds, validations, installs, status).

---

## N

**NEXUS**
: Self-evolving module system. Acronym origin unclear, but represents the "nexus" (connection point) between LLMs and external data sources.

---

## O

**Orchestrator**
: Unified service (port 50054 gRPC, 8003 Admin API) that coordinates task execution, LIDM routing, tool calling, and module management. Replaced previous supervisor-worker mesh.

---

## P

**Pipeline UI**
: React Flow-based visualization (http://localhost:5001/pipeline) showing live service health and module status via SSE.

**Platform**
: Specific service or API an adapter integrates with (e.g., "openweather", "cibc", "clashroyale").

**Prometheus**
: Time-series database (port 9090) for metrics collection and alerting.

---

## R

**RAG (Retrieval-Augmented Generation)**
: Pattern where LLM queries vector database (ChromaDB) for relevant context before generating response.

**React Flow**
: JavaScript library for building node-based UIs. Used in Pipeline visualization.

**Registry**
: See Module Registry or Adapter Registry (context-dependent).

---

## S

**Sandbox Service**
: gRPC service (port 50057) for isolated Python code execution. Used for validating untrusted module code.

**SSE (Server-Sent Events)**
: One-way HTTP streaming from server to client. Used for Pipeline UI live updates (`/stream/pipeline-state`).

**SRP (Single Responsibility Principle)**
: SOLID principle - each module/class should have one reason to change. Refactored in context formatters (moved to dashboard service).

---

## T

**Tier**
: LIDM routing target. Standard (fast, small model) or Heavy (slow, large model). Ultra tier reserved for future use.

**Tool Calling**
: LLM feature where model can invoke functions (tools) during generation. Orchestrator executes tools and synthesizes results.

**Track A/B/C**
: Implementation phases. Track A (self-evolution), Track B (observability), Track C (co-evolution).

---

## U

**UI Service**
: Next.js frontend (port 5001) providing user interface, Pipeline visualization, and settings management.

**Unified Orchestrator**
: See Orchestrator. Emphasizes replacement of previous multi-agent supervisor-worker architecture.

---

## Z

**Zustand**
: State management library for React. Used in Pipeline UI for SSE connection state and module actions.

---

## Acronyms

- **API**: Application Programming Interface
- **CIBC**: Canadian Imperial Bank of Commerce (adapter example)
- **CORS**: Cross-Origin Resource Sharing
- **CPU**: Central Processing Unit
- **CRUD**: Create, Read, Update, Delete
- **CSV**: Comma-Separated Values
- **DB**: Database
- **E2E**: End-to-End (testing)
- **ELK**: Elasticsearch, Logstash, Kibana (planned logging stack)
- **gRPC**: Google Remote Procedure Call
- **HMAC**: Hash-based Message Authentication Code
- **HTTP**: HyperText Transfer Protocol
- **JWT**: JSON Web Token
- **LIDM**: Language-Integrated Decision Making
- **LLM**: Large Language Model
- **MCP**: Model Context Protocol (planned tool integration)
- **OAuth**: Open Authorization
- **OCP**: Open-Closed Principle (SOLID)
- **RAG**: Retrieval-Augmented Generation
- **RBAC**: Role-Based Access Control
- **REST**: Representational State Transfer
- **RPC**: Remote Procedure Call
- **SOLID**: Software design principles (SRP, OCP, LSP, ISP, DIP)
- **SQL**: Structured Query Language
- **SRP**: Single Responsibility Principle
- **SSE**: Server-Sent Events
- **TLS**: Transport Layer Security
- **TTL**: Time To Live
- **UI**: User Interface
- **URL**: Uniform Resource Locator
- **UUID**: Universally Unique Identifier
- **XSS**: Cross-Site Scripting

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [EXTENSION-GUIDE.md](./EXTENSION-GUIDE.md) - Building modules
- [API-REFERENCE.md](./API-REFERENCE.md) - API documentation
