# API Reference

Complete reference for all REST and gRPC APIs in the NEXUS system.

## Table of Contents
1. [Admin API (HTTP :8003)](#admin-api)
2. [Dashboard API (HTTP :8001)](#dashboard-api)
3. [gRPC Services](#grpc-services)
4. [Authentication](#authentication)

---

## Admin API

**Base URL**: `http://localhost:8003`

**CORS**: Enabled for all origins (development mode)

### Health & System Info

#### GET /admin/health
Check if Admin API is running.

**Response**:
```json
{
  "status": "healthy",
  "modules_loaded": 3,
  "timestamp": "2026-02-11T12:00:00Z"
}
```

#### GET /admin/system-info
Get orchestrator system information.

**Response**:
```json
{
  "orchestrator": {
    "status": "running",
    "uptime_seconds": 3600,
    "models_loaded": 2,
    "active_sessions": 5
  },
  "modules": {
    "total": 3,
    "enabled": 2,
    "disabled": 1
  },
  "timestamp": "2026-02-11T12:00:00Z"
}
```

---

### Routing Configuration

#### GET /admin/routing-config
Get current routing configuration.

**Response**:
```json
{
  "categories": {
    "general": {
      "tier": "standard",
      "fallback_tier": "heavy"
    },
    "code_generation": {
      "tier": "heavy",
      "fallback_tier": "standard"
    }
  },
  "tiers": {
    "standard": {
      "model": "qwen2.5-0.5b-instruct-q5_k_m.gguf",
      "context_window": 4,
      "temperature": 0.7
    },
    "heavy": {
      "model": "Qwen2.5-14B-Instruct-Q4_K.gguf",
      "context_window": 6,
      "temperature": 0.7
    }
  },
  "providers": {
    "local": {
      "models": ["qwen2.5-3b-instruct-q5_k_m", "Qwen2.5-14B-Instruct-Q4_K"],
      "default": "qwen2.5-3b-instruct-q5_k_m"
    }
  },
  "lidm_tier_models": {
    "heavy": ["Qwen2.5-14B-Instruct-Q4_K.gguf"],
    "standard": ["qwen2.5-0.5b-instruct-q5_k_m.gguf"]
  }
}
```

#### PUT /admin/routing-config
Update routing configuration (hot-reload).

**Request Body**:
```json
{
  "categories": { ... },
  "tiers": { ... }
}
```

**Response**:
```json
{
  "message": "Configuration updated successfully",
  "reloaded": true
}
```

---

### Module Management

#### GET /admin/modules
List all modules with status and credentials.

**Response**:
```json
{
  "modules": [
    {
      "category": "weather",
      "platform": "openweather",
      "version": "1.0.0",
      "status": "enabled",
      "enabled_at": "2026-02-10T10:00:00Z",
      "has_credentials": true,
      "credentials_valid": true
    },
    {
      "category": "gaming",
      "platform": "clashroyale",
      "version": "1.0.0",
      "status": "enabled",
      "enabled_at": "2026-02-10T11:00:00Z",
      "has_credentials": true,
      "credentials_valid": false
    }
  ],
  "total": 2,
  "enabled": 2,
  "disabled": 0
}
```

#### GET /admin/modules/{category}/{platform}
Get details for a specific module.

**Path Parameters**:
- `category` - Module category (e.g., "weather")
- `platform` - Platform name (e.g., "openweather")

**Response**:
```json
{
  "category": "weather",
  "platform": "openweather",
  "version": "1.0.0",
  "status": "enabled",
  "enabled_at": "2026-02-10T10:00:00Z",
  "manifest": {
    "name": "openweather",
    "description": "OpenWeather API integration",
    "required_credentials": ["api_key"]
  },
  "has_credentials": true,
  "credentials_valid": true
}
```

#### POST /admin/modules/{category}/{platform}/enable
Enable a module.

**Response**:
```json
{
  "message": "Module enabled successfully",
  "category": "weather",
  "platform": "openweather",
  "status": "enabled"
}
```

#### POST /admin/modules/{category}/{platform}/disable
Disable a module.

**Response**:
```json
{
  "message": "Module disabled successfully",
  "category": "weather",
  "platform": "openweather",
  "status": "disabled"
}
```

#### POST /admin/modules/{category}/{platform}/reload
Reload a module (reimport code).

**Response**:
```json
{
  "message": "Module reloaded successfully",
  "category": "weather",
  "platform": "openweather"
}
```

#### DELETE /admin/modules/{category}/{platform}
Uninstall a module (remove from registry).

**Response**:
```json
{
  "message": "Module uninstalled successfully",
  "category": "weather",
  "platform": "openweather"
}
```

---

### Credential Management

#### POST /admin/credentials
Store encrypted credentials for a platform.

**Request Body**:
```json
{
  "platform": "openweather",
  "credentials": {
    "api_key": "your-api-key-here"
  }
}
```

**Response**:
```json
{
  "message": "Credentials stored successfully",
  "platform": "openweather"
}
```

#### GET /admin/credentials/{platform}
Check if credentials exist for a platform (does NOT return actual credentials).

**Response**:
```json
{
  "platform": "openweather",
  "has_credentials": true,
  "fields": ["api_key"]
}
```

#### GET /admin/credentials/{platform}/check
Check if credentials are valid (via dashboard service proxy).

**Response**:
```json
{
  "platform": "openweather",
  "valid": true,
  "checked_at": "2026-02-11T12:00:00Z"
}
```

---

## Dashboard API

**Base URL**: `http://localhost:8001`

### Health

#### GET /health
Check if Dashboard service is running.

**Response**:
```json
{
  "status": "healthy",
  "adapters_loaded": 5,
  "timestamp": "2026-02-11T12:00:00Z"
}
```

---

### Context Aggregation

#### GET /context
Get full aggregated context from all enabled adapters.

**Response**:
```json
{
  "calendar": {
    "today_events": [...],
    "upcoming_events": [...]
  },
  "weather": {
    "current": {...},
    "forecast": [...]
  },
  "finance": {
    "recent_transactions": [...],
    "monthly_summary": {...}
  },
  "gaming": {
    "profile": {...},
    "recent_matches": [...]
  },
  "timestamp": "2026-02-11T12:00:00Z"
}
```

#### GET /context/summary?destination={destination}
Get formatted summary for a specific destination.

**Query Parameters**:
- `destination` (optional) - Destination type (e.g., "work", "home", "gym")

**Response** (plain text):
```
📅 CALENDAR SUMMARY
- Today: Team standup at 10am, Lunch with Sarah at 12pm
- Tomorrow: Dentist appointment at 9am

💰 FINANCE SUMMARY
- This month: Spent $2,450 (Groceries: $450, Transport: $120)
- Recent: Starbucks $5.75, Uber $15.50

☀️ WEATHER SUMMARY
- Current: 72°F, Partly cloudy
- Tomorrow: High 75°F, Low 65°F

🎮 GAMING SUMMARY
- Clash Royale: Level 12, 5500 trophies
- Last match: Victory vs PlayerX (3-1)
```

#### GET /context/briefing
Get daily briefing with high-priority alerts.

**Response** (plain text):
```
🌅 GOOD MORNING BRIEFING

HIGH PRIORITY:
⚠️ Dentist appointment in 30 minutes
⚠️ Low balance alert: $150 remaining

TODAY'S SCHEDULE:
- 9am: Dentist (789 Oak St)
- 12pm: Lunch with Sarah
- 3pm: Team meeting

WEATHER:
- Morning: 65°F, Sunny
- Afternoon: 72°F, Partly cloudy

FINANCE:
- Yesterday: Spent $45.50
- Month to date: $2,450
```

#### GET /context/relevance
Get context classified by relevance (low/medium/high).

**Response**:
```json
{
  "high": [
    {"type": "calendar", "data": "Dentist in 30 min", "priority": 9},
    {"type": "finance", "data": "Low balance", "priority": 8}
  ],
  "medium": [
    {"type": "weather", "data": "Rain later today", "priority": 5}
  ],
  "low": [
    {"type": "gaming", "data": "New season started", "priority": 2}
  ]
}
```

---

### Adapter Management

#### GET /adapters
List all registered adapters with status.

**Response**:
```json
{
  "adapters": [
    {
      "category": "weather",
      "platform": "openweather",
      "enabled": true,
      "has_credentials": true
    },
    {
      "category": "finance",
      "platform": "cibc",
      "enabled": true,
      "has_credentials": false
    }
  ],
  "total": 2,
  "enabled": 2
}
```

---

### Finance (Bank)

#### GET /bank/transactions
Get recent bank transactions.

**Query Parameters**:
- `per_page` (default: 20) - Number of transactions
- `sort_dir` (default: "desc") - Sort direction ("asc" or "desc")

**Response**:
```json
{
  "transactions": [
    {
      "id": "bank:2026-02-11:starbucks",
      "timestamp": "2026-02-11T08:30:00Z",
      "amount": -5.75,
      "currency": "CAD",
      "category": "Food & Dining",
      "merchant": "Starbucks",
      "account_id": "chequing",
      "pending": false,
      "platform": "cibc"
    }
  ],
  "recent_count": 6845,
  "total_expenses_period": 2450.00,
  "total_income_period": 3500.00,
  "net_cashflow": 1050.00,
  "platforms": ["cibc"]
}
```

#### GET /bank/summary
Get financial summary with category breakdowns.

**Response**:
```json
{
  "total_count": 6845,
  "date_range": {
    "earliest": "2022-01-01",
    "latest": "2026-02-11"
  },
  "by_category": {
    "Food & Dining": 450.50,
    "Transport": 120.00,
    "Entertainment": 85.00
  },
  "by_month": {
    "2026-02": 2450.00,
    "2026-01": 2800.00
  },
  "monthly_average": 2625.00
}
```

#### GET /bank/categories
Get list of spending categories.

**Response**:
```json
{
  "categories": [
    "Food & Dining",
    "Transport",
    "Entertainment",
    "Shopping",
    "Bills & Utilities",
    "Health & Fitness",
    "Other"
  ],
  "total": 7
}
```

#### GET /bank/search?query={query}
Search transactions by merchant or description.

**Query Parameters**:
- `query` (required) - Search term

**Response**:
```json
{
  "transactions": [...],
  "total_found": 12,
  "query": "starbucks"
}
```

---

### Pipeline State (SSE)

#### GET /stream/pipeline-state
Server-Sent Events stream of pipeline state (2-second interval).

**Response** (SSE stream):
```
event: pipeline-state
data: {"services": {...}, "modules": [...], "timestamp": "..."}

event: pipeline-state
data: {"services": {...}, "modules": [...], "timestamp": "..."}
```

**Event Data**:
```json
{
  "services": {
    "orchestrator": {"healthy": true, "latency_ms": 12},
    "dashboard": {"healthy": true, "latency_ms": 5},
    "llm": {"healthy": true, "latency_ms": 150},
    "chroma": {"healthy": true, "latency_ms": 8},
    "sandbox": {"healthy": true, "latency_ms": 20}
  },
  "modules": [
    {"category": "weather", "platform": "openweather", "status": "enabled"},
    {"category": "gaming", "platform": "clashroyale", "status": "enabled"}
  ],
  "pipeline_stages": ["ingest", "aggregate", "synthesize", "deliver"],
  "timestamp": "2026-02-11T12:00:00Z"
}
```

---

### Modules

#### GET /modules
List all dynamically loaded modules.

**Response**:
```json
{
  "modules": [
    {
      "category": "weather",
      "platform": "openweather",
      "version": "1.0.0",
      "status": "enabled"
    },
    {
      "category": "showroom",
      "platform": "metrics_demo",
      "version": "1.0.0",
      "status": "disabled"
    }
  ],
  "total": 2
}
```

---

## gRPC Services

### Orchestrator Service

**Host**: `localhost:50054`

**Proto**: `shared/proto/orchestrator_service.proto`

#### ExecuteTask

Execute a task with LLM.

**Request**:
```protobuf
message ExecuteTaskRequest {
  string user_id = 1;
  string task_description = 2;
  repeated Message conversation_history = 3;
  map<string, string> metadata = 4;
}
```

**Response**:
```protobuf
message ExecuteTaskResponse {
  string task_id = 1;
  string result = 2;
  string status = 3;
  repeated ToolCall tool_calls = 4;
  map<string, string> metadata = 5;
}
```

#### StreamTask

Execute a task with streaming response.

**Request**: Same as `ExecuteTaskRequest`

**Response Stream**:
```protobuf
message StreamChunk {
  string chunk = 1;
  bool is_complete = 2;
}
```

#### GetHistory

Get conversation history for a user.

**Request**:
```protobuf
message GetHistoryRequest {
  string user_id = 1;
  int32 limit = 2;
}
```

**Response**:
```protobuf
message GetHistoryResponse {
  repeated Message messages = 1;
}
```

---

### LLM Service

**Host**: `localhost:50051`

**Proto**: `shared/proto/llm_service.proto`

#### Generate

Generate text completion.

**Request**:
```protobuf
message GenerateRequest {
  string prompt = 1;
  string model = 2;
  float temperature = 3;
  int32 max_tokens = 4;
}
```

**Response**:
```protobuf
message GenerateResponse {
  string generated_text = 1;
  int32 tokens_used = 2;
  float inference_time_ms = 3;
}
```

#### StreamGenerate

Generate with streaming output.

**Request**: Same as `GenerateRequest`

**Response Stream**:
```protobuf
message StreamChunk {
  string text = 1;
  bool is_final = 2;
}
```

---

### Chroma Service

**Host**: `localhost:50052`

**Proto**: `shared/proto/chroma_service.proto`

#### Store

Store documents in vector database.

**Request**:
```protobuf
message StoreRequest {
  string collection_name = 1;
  repeated Document documents = 2;
}

message Document {
  string id = 1;
  string text = 2;
  map<string, string> metadata = 3;
}
```

**Response**:
```protobuf
message StoreResponse {
  bool success = 1;
  int32 documents_stored = 2;
}
```

#### Query

Query vector database with semantic search.

**Request**:
```protobuf
message QueryRequest {
  string collection_name = 1;
  string query_text = 2;
  int32 n_results = 3;
}
```

**Response**:
```protobuf
message QueryResponse {
  repeated QueryResult results = 1;
}

message QueryResult {
  string document_id = 1;
  string text = 2;
  float distance = 3;
  map<string, string> metadata = 4;
}
```

---

### Sandbox Service

**Host**: `localhost:50057`

**Proto**: `shared/proto/sandbox_service.proto`

#### ExecuteCode

Execute Python code in isolated sandbox.

**Request**:
```protobuf
message ExecuteCodeRequest {
  string code = 1;
  string language = 2; // "python"
  int32 timeout_seconds = 3;
  map<string, string> env_vars = 4;
}
```

**Response**:
```protobuf
message ExecuteCodeResponse {
  string stdout = 1;
  string stderr = 2;
  int32 exit_code = 3;
  bool timeout = 4;
  float execution_time_ms = 5;
}
```

---

## Authentication

**Current Status**: No authentication (development mode)

**Planned** (Q2 2026):
- OAuth2 for Admin API
- API keys for Dashboard API
- JWT tokens for gRPC services
- Role-based access control (RBAC)

---

## Error Responses

All HTTP endpoints return JSON errors in this format:

```json
{
  "error": "Module not found",
  "details": "No module registered for category=weather, platform=invalid",
  "timestamp": "2026-02-11T12:00:00Z"
}
```

**Common HTTP Status Codes**:
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (module/endpoint doesn't exist)
- `500` - Internal Server Error

**gRPC Status Codes**:
- `OK` (0) - Success
- `INVALID_ARGUMENT` (3) - Bad parameters
- `NOT_FOUND` (5) - Resource not found
- `UNAVAILABLE` (14) - Service unavailable
- `INTERNAL` (13) - Internal error

---

## Rate Limiting

**Current**: None

**Planned**: Per-endpoint rate limiting with Redis backend

---

## Versioning

**Current**: No versioning (all endpoints are v1 implicitly)

**Planned**: URL-based versioning (`/v2/admin/modules`)

---

## Examples

### Enable a Module via curl

```bash
curl -X POST http://localhost:8003/admin/modules/weather/openweather/enable
```

### Get Context Summary

```bash
curl http://localhost:8001/context/summary?destination=work
```

### Store Credentials

```bash
curl -X POST http://localhost:8003/admin/credentials \
  -H "Content-Type: application/json" \
  -d '{"platform": "openweather", "credentials": {"api_key": "your-key"}}'
```

### List Modules

```bash
curl http://localhost:8003/admin/modules | jq .
```

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [EXTENSION-GUIDE.md](./EXTENSION-GUIDE.md) - Building modules
- [OPERATIONS.md](./OPERATIONS.md) - Monitoring and troubleshooting
