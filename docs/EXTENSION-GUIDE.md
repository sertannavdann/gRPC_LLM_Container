# Extension Guide: Building NEXUS Modules

Learn how to extend NEXUS with custom adapters and modules.

## Table of Contents
1. [Module System Overview](#module-system-overview)
2. [Quick Start: Your First Module](#quick-start-your-first-module)
3. [Module Structure](#module-structure)
4. [Adapter Patterns](#adapter-patterns)
5. [Credential Management](#credential-management)
6. [Testing Modules](#testing-modules)
7. [Module Lifecycle](#module-lifecycle)
8. [Troubleshooting](#troubleshooting)
9. [Complete Example: Weather Adapter](#complete-example-weather-adapter)

---

## Module System Overview

### Philosophy

NEXUS modules are **self-contained adapters** that:
- Fetch data from external sources (APIs, files, databases)
- Transform data to canonical schemas
- Register themselves dynamically at runtime
- Can be enabled/disabled without restarting services

### Architecture

```
modules/
├── {category}/
│   └── {platform}/
│       ├── manifest.json      # Module metadata
│       ├── adapter.py          # Adapter implementation
│       └── test_adapter.py     # Unit tests
```

### Key Concepts

- **Category**: Broad classification (e.g., "weather", "finance", "gaming")
- **Platform**: Specific service (e.g., "openweather", "cibc", "clashroyale")
- **Manifest**: JSON schema defining module metadata
- **Adapter**: Python class extending `BaseAdapter[T]`
- **Canonical Schema**: Pydantic models in `shared/schemas/canonical.py`

---

## Quick Start: Your First Module

Let's build a simple "Hello World" module.

### Step 1: Create Directory

```bash
mkdir -p modules/test/hello
cd modules/test/hello
```

### Step 2: Create Manifest

Create `manifest.json`:

```json
{
  "name": "hello",
  "category": "test",
  "platform": "hello",
  "version": "1.0.0",
  "adapter_class": "HelloAdapter",
  "adapter_file": "adapter.py",
  "required_credentials": [],
  "description": "Simple hello world module"
}
```

### Step 3: Implement Adapter

Create `adapter.py`:

```python
from typing import Any, Dict
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter

@register_adapter
class HelloAdapter(BaseAdapter[Dict[str, str]]):
    """Simple hello world adapter."""

    def __init__(self):
        super().__init__(
            category="test",
            platform="hello",
            credentials_required=[]
        )

    async def fetch_raw(self) -> Any:
        """Fetch raw data (simulate API call)."""
        return {"message": "Hello from NEXUS!"}

    def transform(self, raw_data: Any) -> AdapterResult[Dict[str, str]]:
        """Transform to canonical format."""
        return AdapterResult(
            data={"greeting": raw_data["message"]},
            metadata={"source": "hello_adapter"}
        )
```

### Step 4: Create Tests

Create `test_adapter.py`:

```python
import pytest
from adapter import HelloAdapter

@pytest.mark.asyncio
async def test_hello_adapter():
    """Test Hello adapter."""
    adapter = HelloAdapter()

    # Fetch
    raw = await adapter.fetch_raw()
    assert raw["message"] == "Hello from NEXUS!"

    # Transform
    result = adapter.transform(raw)
    assert result.data["greeting"] == "Hello from NEXUS!"
```

### Step 5: Install Module

```bash
# Via Admin API
curl -X POST http://localhost:8003/admin/modules/test/hello/enable

# Or via Makefile (add custom target)
```

### Step 6: Verify

```bash
# Check module is loaded
curl http://localhost:8003/admin/modules | jq '.modules[] | select(.platform=="hello")'

# Check dashboard recognizes it
curl http://localhost:8001/adapters | jq '.adapters[] | select(.platform=="hello")'
```

---

## Module Structure

### Manifest Schema

**File**: `manifest.json`

```json
{
  "name": "string",              // Unique module name
  "category": "string",          // Category (can be custom)
  "platform": "string",          // Platform identifier
  "version": "string",           // Semantic version (e.g., "1.0.0")
  "adapter_class": "string",     // Python class name
  "adapter_file": "string",      // Python file name (usually "adapter.py")
  "required_credentials": [],    // List of credential keys
  "description": "string",       // Human-readable description
  "author": "string" (optional), // Module author
  "license": "string" (optional) // License (e.g., "MIT")
}
```

### Adapter Class

All adapters extend `BaseAdapter[T]` where `T` is the canonical schema type.

**Required Methods**:
- `async def fetch_raw(self) -> Any` - Fetch data from external source
- `def transform(self, raw_data: Any) -> AdapterResult[T]` - Transform to canonical schema

**Optional Methods**:
- `def __init__(self)` - Initialize adapter, set credentials_required
- `async def fetch(self) -> AdapterResult[T]` - Override to customize fetch logic

### Canonical Schemas

**Location**: `shared/schemas/canonical.py`

**Existing Schemas**:
- `FinancialTransaction` - Bank transactions
- `CalendarEvent` - Calendar events
- `WeatherData` - Current weather
- `WeatherForecast` - Weather forecast
- `GamingProfile` - Gaming profile
- `GamingMatch` - Gaming match results
- `HealthMetric` - Health/fitness data
- `NavigationRoute` - Navigation directions

**Creating Custom Schemas**:

```python
from pydantic import BaseModel
from typing import Optional

class MyCustomSchema(BaseModel):
    """Custom data schema."""
    id: str
    timestamp: str
    value: float
    metadata: Optional[dict] = None
```

### AdapterResult

**Structure**:

```python
@dataclass
class AdapterResult(Generic[T]):
    data: T                         # Canonical schema instance
    metadata: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
```

**Example**:

```python
return AdapterResult(
    data=WeatherData(...),
    metadata={"source": "openweather", "cache_hit": False},
    errors=[]
)
```

---

## Adapter Patterns

### Pattern 1: REST API Adapter

```python
import httpx
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter
from shared.schemas.canonical import WeatherData

@register_adapter
class OpenWeatherAdapter(BaseAdapter[WeatherData]):
    """OpenWeather API adapter."""

    def __init__(self):
        super().__init__(
            category="weather",
            platform="openweather",
            credentials_required=["api_key"]
        )

    async def fetch_raw(self) -> Any:
        """Fetch from OpenWeather API."""
        api_key = self._get_credential("api_key")
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Toronto&appid={api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    def transform(self, raw_data: Any) -> AdapterResult[WeatherData]:
        """Transform to canonical schema."""
        return AdapterResult(
            data=WeatherData(
                timestamp=str(raw_data["dt"]),
                temperature=raw_data["main"]["temp"],
                condition=raw_data["weather"][0]["main"],
                humidity=raw_data["main"]["humidity"],
                location="Toronto"
            ),
            metadata={"source": "openweather"}
        )
```

### Pattern 2: CSV File Adapter

```python
import csv
from pathlib import Path
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter
from shared.schemas.canonical import FinancialTransaction

@register_adapter
class CIBCAdapter(BaseAdapter[list[FinancialTransaction]]):
    """CIBC CSV bank statement adapter."""

    def __init__(self):
        super().__init__(
            category="finance",
            platform="cibc",
            credentials_required=[]  # No credentials (local files)
        )

    async def fetch_raw(self) -> Any:
        """Read CSV files from Bank/ directory."""
        csv_path = Path("/app/dashboard_service/Bank/cibc.csv")

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def transform(self, raw_data: Any) -> AdapterResult[list[FinancialTransaction]]:
        """Transform CSV rows to canonical transactions."""
        transactions = []

        for row in raw_data:
            transactions.append(FinancialTransaction(
                id=f"cibc:{row['timestamp']}:{row['merchant']}",
                timestamp=row["timestamp"],
                amount=float(row["amount"]),
                currency="CAD",
                merchant=(row.get("merchant") or "").strip(),
                category=row.get("spending_category", "Other")
            ))

        return AdapterResult(
            data=transactions,
            metadata={"source": "cibc", "count": len(transactions)}
        )
```

### Pattern 3: Database Adapter

```python
import asyncpg
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter

@register_adapter
class PostgresAdapter(BaseAdapter[list[dict]]):
    """PostgreSQL database adapter."""

    def __init__(self):
        super().__init__(
            category="database",
            platform="postgres",
            credentials_required=["host", "port", "user", "password", "database"]
        )

    async def fetch_raw(self) -> Any:
        """Query PostgreSQL database."""
        conn = await asyncpg.connect(
            host=self._get_credential("host"),
            port=self._get_credential("port"),
            user=self._get_credential("user"),
            password=self._get_credential("password"),
            database=self._get_credential("database")
        )

        rows = await conn.fetch("SELECT * FROM my_table LIMIT 100")
        await conn.close()

        return [dict(row) for row in rows]

    def transform(self, raw_data: Any) -> AdapterResult[list[dict]]:
        """Pass through (already in dict format)."""
        return AdapterResult(
            data=raw_data,
            metadata={"source": "postgres", "count": len(raw_data)}
        )
```

### Pattern 4: Synthetic Data Adapter (for demos)

```python
import random
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter

@register_adapter
class MetricsDemoAdapter(BaseAdapter[dict]):
    """Synthetic metrics adapter for demos."""

    def __init__(self):
        super().__init__(
            category="showroom",
            platform="metrics_demo",
            credentials_required=[]
        )

    async def fetch_raw(self) -> Any:
        """Generate synthetic metrics."""
        return {
            "latency_ms": random.uniform(10, 200),
            "throughput": random.randint(100, 1000),
            "errors": random.randint(0, 10),
            "cpu_percent": random.uniform(20, 80),
            "memory_mb": random.uniform(100, 500)
        }

    def transform(self, raw_data: Any) -> AdapterResult[dict]:
        """Pass through synthetic data."""
        return AdapterResult(
            data=raw_data,
            metadata={"source": "synthetic"}
        )
```

---

## Credential Management

### Storing Credentials

**Via Admin API**:

```bash
curl -X POST http://localhost:8003/admin/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "openweather",
    "credentials": {
      "api_key": "your-api-key-here"
    }
  }'
```

**Via Python** (in adapter code):

```python
# DON'T: Hardcode credentials
api_key = "hardcoded-key"  # ❌

# DO: Use credential store
api_key = self._get_credential("api_key")  # ✅
```

### Accessing Credentials

**In Adapter**:

```python
class MyAdapter(BaseAdapter[T]):
    def __init__(self):
        super().__init__(
            category="my_category",
            platform="my_platform",
            credentials_required=["api_key", "secret"]
        )

    async def fetch_raw(self) -> Any:
        api_key = self._get_credential("api_key")
        secret = self._get_credential("secret")
        # Use credentials...
```

**Security Notes**:
- Credentials are Fernet-encrypted at rest
- Never logged or passed to LLM context
- Stored in `data/module_credentials.db` (encrypted)
- Require `MODULE_ENCRYPTION_KEY` env var (32-byte base64)

### Environment Variables

**Alternative**: Use `.env` file (for development):

```bash
# .env
OPENWEATHER_API_KEY=your-key-here
CLASH_ROYALE_API_KEY=your-key-here
```

**Access in adapter**:

```python
import os

api_key = os.getenv("OPENWEATHER_API_KEY")
```

**Note**: Environment variables are less secure than credential store but acceptable for development.

---

## Testing Modules

### Unit Tests

**File**: `test_adapter.py`

```python
import pytest
from adapter import MyAdapter

@pytest.mark.asyncio
async def test_my_adapter_fetch():
    """Test raw data fetching."""
    adapter = MyAdapter()
    raw = await adapter.fetch_raw()

    assert raw is not None
    assert "expected_field" in raw

@pytest.mark.asyncio
async def test_my_adapter_transform():
    """Test data transformation."""
    adapter = MyAdapter()
    raw = {"test": "data"}

    result = adapter.transform(raw)

    assert result.data is not None
    assert result.metadata["source"] == "my_platform"
    assert len(result.errors) == 0
```

### Integration Tests

**Test with dashboard service**:

```bash
# Start services
make docker-up

# Enable your module
curl -X POST http://localhost:8003/admin/modules/my_category/my_platform/enable

# Fetch context (should include your adapter data)
curl http://localhost:8001/context | jq .

# Check adapter status
curl http://localhost:8001/adapters | jq '.adapters[] | select(.platform=="my_platform")'
```

### Sandbox Validation

**Future feature** (Track A4): Modules will be validated in sandbox before installation.

**Manual sandbox test**:

```bash
# Copy module to sandbox
docker cp modules/my_category/my_platform/ sandbox_service:/tmp/

# Execute test in sandbox
docker exec -it sandbox_service python -m pytest /tmp/my_platform/test_adapter.py
```

---

## Module Lifecycle

### States

```
DISCOVERED → LOADED → VALIDATED → INSTALLED → ENABLED
                                              ↓
                                          DISABLED
                                              ↓
                                          UNINSTALLED
```

### Operations

#### Load
```bash
# Automatic: Place module in modules/ directory, restart orchestrator
# Manual: Use module loader
```

#### Enable
```bash
curl -X POST http://localhost:8003/admin/modules/{category}/{platform}/enable
```

#### Disable
```bash
curl -X POST http://localhost:8003/admin/modules/{category}/{platform}/disable
```

#### Reload
```bash
# Reimport module code (for development)
curl -X POST http://localhost:8003/admin/modules/{category}/{platform}/reload
```

#### Uninstall
```bash
# Remove from registry
curl -X DELETE http://localhost:8003/admin/modules/{category}/{platform}
```

### Module Discovery

**Automatic Discovery** (future feature):
- Scan `modules/` directory on startup
- Load manifests
- Register modules automatically

**Current**: Manual enable via Admin API

---

## Troubleshooting

### Module Not Loading

**Symptoms**: Module not in `/admin/modules` list

**Solutions**:
1. Check manifest syntax:
   ```bash
   cat modules/my_category/my_platform/manifest.json | jq .
   ```

2. Check adapter syntax:
   ```bash
   python -m py_compile modules/my_category/my_platform/adapter.py
   ```

3. Check orchestrator logs:
   ```bash
   make logs-core | grep "Module"
   ```

4. Verify directory structure:
   ```bash
   tree modules/my_category/my_platform/
   # Should have: manifest.json, adapter.py, test_adapter.py
   ```

### Credentials Not Working

**Symptoms**: Adapter fails with authentication error

**Solutions**:
1. Check credentials stored:
   ```bash
   curl http://localhost:8003/admin/credentials/my_platform
   ```

2. Verify credential keys match manifest:
   ```bash
   cat modules/my_category/my_platform/manifest.json | jq .required_credentials
   ```

3. Test credential retrieval in adapter:
   ```python
   try:
       api_key = self._get_credential("api_key")
       print(f"Got credential: {api_key[:5]}...")
   except Exception as e:
       print(f"Error: {e}")
   ```

### Data Not Appearing in Context

**Symptoms**: Module enabled but data not in `/context`

**Solutions**:
1. Check adapter is enabled:
   ```bash
   curl http://localhost:8001/adapters | jq '.adapters[] | select(.platform=="my_platform")'
   ```

2. Test adapter directly:
   ```bash
   # Add debug endpoint to dashboard (temporary)
   curl http://localhost:8001/adapters/my_category/my_platform/fetch
   ```

3. Check for exceptions in logs:
   ```bash
   make logs-errors | grep "my_platform"
   ```

4. Verify transform returns correct schema:
   ```python
   result = adapter.transform(raw_data)
   print(result.data)  # Should match canonical schema
   ```

### Module Reload Not Working

**Symptoms**: Code changes not reflected after reload

**Solutions**:
1. Restart orchestrator (hard reload):
   ```bash
   docker-compose restart orchestrator
   ```

2. Clear Python cache:
   ```bash
   find modules/my_category/my_platform/ -type d -name __pycache__ -exec rm -rf {} +
   ```

3. Check for import errors:
   ```bash
   make logs-debug | grep "ImportError"
   ```

---

## Complete Example: Weather Adapter

Here's a production-ready weather adapter with all best practices.

### Directory Structure

```
modules/weather/openweather/
├── manifest.json
├── adapter.py
├── test_adapter.py
└── README.md
```

### manifest.json

```json
{
  "name": "openweather",
  "category": "weather",
  "platform": "openweather",
  "version": "1.0.0",
  "adapter_class": "OpenWeatherAdapter",
  "adapter_file": "adapter.py",
  "required_credentials": ["api_key"],
  "description": "OpenWeather API integration for current weather and forecasts",
  "author": "NEXUS Team",
  "license": "MIT"
}
```

### adapter.py

```python
"""OpenWeather API adapter."""
import httpx
from typing import Any
from shared.adapters.base import BaseAdapter, AdapterResult, register_adapter
from shared.schemas.canonical import WeatherData, WeatherForecast

@register_adapter
class OpenWeatherAdapter(BaseAdapter[dict]):
    """Fetch current weather and forecasts from OpenWeather API."""

    def __init__(self):
        super().__init__(
            category="weather",
            platform="openweather",
            credentials_required=["api_key"]
        )
        self.base_url = "https://api.openweathermap.org/data/2.5"

    async def fetch_raw(self) -> Any:
        """Fetch current weather and 5-day forecast."""
        api_key = self._get_credential("api_key")
        city = "Toronto"  # TODO: Make configurable

        async with httpx.AsyncClient() as client:
            # Fetch current weather
            current_url = f"{self.base_url}/weather?q={city}&appid={api_key}&units=metric"
            current_response = await client.get(current_url)
            current_response.raise_for_status()

            # Fetch forecast
            forecast_url = f"{self.base_url}/forecast?q={city}&appid={api_key}&units=metric"
            forecast_response = await client.get(forecast_url)
            forecast_response.raise_for_status()

            return {
                "current": current_response.json(),
                "forecast": forecast_response.json()
            }

    def transform(self, raw_data: Any) -> AdapterResult[dict]:
        """Transform to canonical schemas."""
        # Transform current weather
        current_raw = raw_data["current"]
        current = WeatherData(
            timestamp=str(current_raw["dt"]),
            temperature=current_raw["main"]["temp"],
            condition=current_raw["weather"][0]["main"],
            humidity=current_raw["main"]["humidity"],
            location=current_raw["name"]
        )

        # Transform forecast
        forecast_raw = raw_data["forecast"]["list"][:5]  # Next 5 periods
        forecasts = [
            WeatherForecast(
                timestamp=str(item["dt"]),
                temperature_high=item["main"]["temp_max"],
                temperature_low=item["main"]["temp_min"],
                condition=item["weather"][0]["main"],
                precipitation_chance=item.get("pop", 0.0) * 100
            )
            for item in forecast_raw
        ]

        return AdapterResult(
            data={
                "current": current.dict(),
                "forecast": [f.dict() for f in forecasts]
            },
            metadata={
                "source": "openweather",
                "city": current_raw["name"],
                "forecast_periods": len(forecasts)
            }
        )
```

### test_adapter.py

```python
"""Tests for OpenWeather adapter."""
import pytest
from unittest.mock import AsyncMock, patch
from adapter import OpenWeatherAdapter

@pytest.fixture
def mock_weather_data():
    """Mock OpenWeather API responses."""
    return {
        "current": {
            "dt": 1707667200,
            "name": "Toronto",
            "main": {"temp": 5.5, "humidity": 65, "temp_max": 7.0, "temp_min": 3.0},
            "weather": [{"main": "Clouds"}]
        },
        "forecast": {
            "list": [
                {
                    "dt": 1707667200,
                    "main": {"temp_max": 7.0, "temp_min": 3.0},
                    "weather": [{"main": "Clouds"}],
                    "pop": 0.2
                }
            ] * 5
        }
    }

@pytest.mark.asyncio
async def test_openweather_adapter_fetch(mock_weather_data):
    """Test fetching from OpenWeather API."""
    adapter = OpenWeatherAdapter()

    with patch.object(adapter, 'fetch_raw', return_value=mock_weather_data):
        raw = await adapter.fetch_raw()

        assert "current" in raw
        assert "forecast" in raw
        assert raw["current"]["name"] == "Toronto"

@pytest.mark.asyncio
async def test_openweather_adapter_transform(mock_weather_data):
    """Test transformation to canonical schema."""
    adapter = OpenWeatherAdapter()
    result = adapter.transform(mock_weather_data)

    assert result.data["current"]["location"] == "Toronto"
    assert result.data["current"]["temperature"] == 5.5
    assert len(result.data["forecast"]) == 5
    assert result.metadata["source"] == "openweather"
```

### README.md

```markdown
# OpenWeather Adapter

OpenWeather API integration for current weather and forecasts.

## Setup

1. Get API key from https://openweathermap.org/api
2. Store credentials:
   ```bash
   curl -X POST http://localhost:8003/admin/credentials \
     -H "Content-Type: application/json" \
     -d '{"platform": "openweather", "credentials": {"api_key": "YOUR_KEY"}}'
   ```

3. Enable module:
   ```bash
   curl -X POST http://localhost:8003/admin/modules/weather/openweather/enable
   ```

## Usage

Get weather context:
```bash
curl http://localhost:8001/context | jq .weather
```

## Testing

```bash
pytest test_adapter.py -v
```
```

---

## Next Steps

1. **Build Your First Module**: Start with the Quick Start section
2. **Study Examples**: Look at `modules/weather/openweather/` and `modules/gaming/clashroyale/`
3. **Read API Reference**: Understand Admin API endpoints in [API-REFERENCE.md](./API-REFERENCE.md)
4. **Join Development**: See [ROADMAP.md](./ROADMAP.md) for Track A4 (LLM-driven module builder)

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [API-REFERENCE.md](./API-REFERENCE.md) - API documentation
- [SECURITY.md](./SECURITY.md) - Credential security
- [GLOSSARY.md](./GLOSSARY.md) - Terms and concepts
