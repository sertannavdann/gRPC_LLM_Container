"""
Observability Tests - Fixtures and Utilities

Provides test fixtures for verifying metrics, traces, and logging in:
- Prometheus (metrics collection and querying)
- Grafana (dashboard availability)
- OpenTelemetry Collector (trace propagation)
- Dashboard Service (HTTP API metrics)
"""
import os
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import pytest
import httpx
import grpc
from grpc import aio

# Import gRPC stubs
from shared.generated import agent_pb2, agent_pb2_grpc

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ObservabilityConfig:
    """Configuration for observability endpoints."""
    prometheus_url: str = "http://localhost:9090"
    grafana_url: str = "http://localhost:3001"
    tempo_url: str = "http://localhost:3200"
    otel_collector_url: str = "http://localhost:13133"
    dashboard_url: str = "http://localhost:8001"
    orchestrator_grpc: str = "localhost:50054"
    orchestrator_metrics: str = "http://localhost:8888"
    
    # Timeouts and retries
    scrape_interval: float = 15.0  # Prometheus scrape interval
    retry_attempts: int = 5
    retry_delay: float = 2.0


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def obs_config() -> ObservabilityConfig:
    """Get observability configuration from environment or defaults."""
    return ObservabilityConfig(
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
        grafana_url=os.getenv("GRAFANA_URL", "http://localhost:3001"),
        tempo_url=os.getenv("TEMPO_URL", "http://localhost:3200"),
        otel_collector_url=os.getenv("OTEL_COLLECTOR_URL", "http://localhost:13133"),
        dashboard_url=os.getenv("DASHBOARD_URL", "http://localhost:8001"),
        orchestrator_grpc=os.getenv("ORCHESTRATOR_GRPC", "localhost:50054"),
        orchestrator_metrics=os.getenv("ORCHESTRATOR_METRICS", "http://localhost:8888"),
    )


@pytest.fixture(scope="session")
def http_client() -> httpx.Client:
    """Synchronous HTTP client for API calls."""
    return httpx.Client(timeout=30.0)


@pytest.fixture(scope="session")
def async_http_client() -> httpx.AsyncClient:
    """Async HTTP client for API calls."""
    return httpx.AsyncClient(timeout=30.0)


@pytest.fixture(scope="session")
def prometheus_client(obs_config: ObservabilityConfig, http_client: httpx.Client) -> "PrometheusClient":
    """Prometheus query client."""
    return PrometheusClient(obs_config.prometheus_url, http_client)


@pytest.fixture(scope="session")
def grafana_client(obs_config: ObservabilityConfig, http_client: httpx.Client) -> "GrafanaClient":
    """Grafana API client."""
    return GrafanaClient(obs_config.grafana_url, http_client)


@pytest.fixture(scope="function")
async def grpc_client(obs_config: ObservabilityConfig):
    """gRPC client for orchestrator."""
    channel = aio.insecure_channel(obs_config.orchestrator_grpc)
    stub = agent_pb2_grpc.AgentServiceStub(channel)
    yield stub
    await channel.close()


# =============================================================================
# PROMETHEUS CLIENT
# =============================================================================

class PrometheusClient:
    """
    Client for querying Prometheus metrics.
    
    Provides methods to query instant values, ranges, and verify metric existence.
    """
    
    def __init__(self, base_url: str, client: httpx.Client):
        self.base_url = base_url.rstrip("/")
        self.client = client
    
    def query(self, promql: str) -> Dict[str, Any]:
        """
        Execute an instant query.
        
        Args:
            promql: PromQL query string
            
        Returns:
            Query result with status and data
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/query",
            params={"query": promql}
        )
        response.raise_for_status()
        return response.json()
    
    def query_range(
        self,
        promql: str,
        start: float,
        end: float,
        step: str = "15s"
    ) -> Dict[str, Any]:
        """
        Execute a range query.
        
        Args:
            promql: PromQL query string
            start: Start timestamp (Unix)
            end: End timestamp (Unix)
            step: Query resolution step
            
        Returns:
            Query result with status and data
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/query_range",
            params={
                "query": promql,
                "start": start,
                "end": end,
                "step": step,
            }
        )
        response.raise_for_status()
        return response.json()
    
    def get_metric_value(self, promql: str) -> Optional[float]:
        """
        Get a single metric value.
        
        Args:
            promql: PromQL query string
            
        Returns:
            Metric value or None if not found
        """
        result = self.query(promql)
        if result.get("status") != "success":
            return None
        
        data = result.get("data", {})
        results = data.get("result", [])
        
        if not results:
            return None
        
        # Get the first result's value
        value = results[0].get("value", [])
        if len(value) >= 2:
            return float(value[1])
        
        return None
    
    def metric_exists(self, metric_name: str, labels: Optional[Dict[str, str]] = None) -> bool:
        """
        Check if a metric exists with optional label filtering.
        
        Args:
            metric_name: Name of the metric
            labels: Optional label filters
            
        Returns:
            True if metric exists with data
        """
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            promql = f"{metric_name}{{{label_str}}}"
        else:
            promql = metric_name
        
        result = self.query(promql)
        return (
            result.get("status") == "success" and
            len(result.get("data", {}).get("result", [])) > 0
        )
    
    def wait_for_metric(
        self,
        metric_name: str,
        timeout: float = 60.0,
        poll_interval: float = 5.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Wait for a metric to appear in Prometheus.
        
        Args:
            metric_name: Name of the metric
            timeout: Maximum wait time in seconds
            poll_interval: Time between checks
            labels: Optional label filters
            
        Returns:
            True if metric appeared within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.metric_exists(metric_name, labels):
                return True
            time.sleep(poll_interval)
        return False
    
    def get_all_metric_names(self) -> List[str]:
        """Get all metric names from Prometheus."""
        response = self.client.get(f"{self.base_url}/api/v1/label/__name__/values")
        response.raise_for_status()
        result = response.json()
        return result.get("data", [])


# =============================================================================
# GRAFANA CLIENT
# =============================================================================

class GrafanaClient:
    """
    Client for Grafana API.
    
    Provides methods to check dashboard availability and health.
    """
    
    def __init__(
        self,
        base_url: str,
        client: httpx.Client,
        username: str = "admin",
        password: str = "admin"
    ):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.auth = (username, password)
    
    def health_check(self) -> bool:
        """Check if Grafana is healthy."""
        try:
            response = self.client.get(f"{self.base_url}/api/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def list_dashboards(self) -> List[Dict[str, Any]]:
        """List all dashboards."""
        response = self.client.get(
            f"{self.base_url}/api/search",
            auth=self.auth,
            params={"type": "dash-db"}
        )
        response.raise_for_status()
        return response.json()
    
    def get_dashboard(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Get a dashboard by UID.
        
        Args:
            uid: Dashboard UID
            
        Returns:
            Dashboard data or None if not found
        """
        try:
            response = self.client.get(
                f"{self.base_url}/api/dashboards/uid/{uid}",
                auth=self.auth
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None
    
    def dashboard_exists(self, uid: str) -> bool:
        """Check if a dashboard exists."""
        return self.get_dashboard(uid) is not None
    
    def list_datasources(self) -> List[Dict[str, Any]]:
        """List all datasources."""
        response = self.client.get(
            f"{self.base_url}/api/datasources",
            auth=self.auth
        )
        response.raise_for_status()
        return response.json()
    
    def datasource_healthy(self, name: str) -> bool:
        """Check if a datasource is healthy."""
        try:
            # First get the datasource ID
            datasources = self.list_datasources()
            ds = next((d for d in datasources if d["name"] == name), None)
            if not ds:
                return False
            
            # Check health
            response = self.client.get(
                f"{self.base_url}/api/datasources/{ds['id']}/health",
                auth=self.auth
            )
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# TEST SCENARIOS
# =============================================================================

class TestScenarios:
    """
    Reusable test scenarios that trigger specific observability events.
    
    Use these to generate metrics/traces for E2E verification.
    """
    
    def __init__(self, config: ObservabilityConfig):
        self.config = config
    
    async def send_simple_query(self, query: str = "Hello, world!") -> Dict[str, Any]:
        """
        Send a simple query to the orchestrator.
        
        Returns metadata about the request for verification.
        """
        channel = aio.insecure_channel(self.config.orchestrator_grpc)
        stub = agent_pb2_grpc.AgentServiceStub(channel)
        
        start_time = time.time()
        test_id = f"test-{int(time.time())}"
        try:
            # type: ignore is needed because protobuf generates classes dynamically
            request = agent_pb2.AgentRequest(  # type: ignore[attr-defined]
                user_query=query,
                debug_mode=True,  # Enable debug mode for testing
            )
            response = await stub.QueryAgent(request, timeout=60.0)
            latency = (time.time() - start_time) * 1000
            
            return {
                "success": True,
                "latency_ms": latency,
                "response": response.final_answer,
                "test_id": test_id,
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "error": str(e),
                "latency_ms": (time.time() - start_time) * 1000,
            }
        finally:
            await channel.close()
    
    async def send_tool_query(self) -> Dict[str, Any]:
        """Send a query that triggers tool usage."""
        return await self.send_simple_query(
            "Search the web for the latest news about AI."
        )
    
    async def send_multi_tool_query(self) -> Dict[str, Any]:
        """Send a query that triggers multiple tools."""
        return await self.send_simple_query(
            "What time is my next meeting and how long will it take to get there?"
        )
    
    async def trigger_provider_fallback(self) -> Dict[str, Any]:
        """
        Attempt to trigger provider fallback behavior.
        
        This sends a complex query that might exceed local model capabilities.
        """
        return await self.send_simple_query(
            "Write a detailed analysis of the economic implications of "
            "quantum computing on the financial services industry, including "
            "specific use cases and timeline predictions."
        )
    
    def fetch_dashboard_context(self, user_id: str = "test-user") -> Dict[str, Any]:
        """Fetch context from the dashboard service."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{self.config.dashboard_url}/context",
                params={"user_id": user_id}
            )
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": response.json() if response.status_code == 200 else None,
            }
    
    def trigger_dashboard_cache_miss(self) -> Dict[str, Any]:
        """Force a cache miss by requesting with force_refresh."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{self.config.dashboard_url}/context",
                params={"user_id": f"test-{int(time.time())}", "force_refresh": "true"}
            )
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
            }


@pytest.fixture(scope="session")
def test_scenarios(obs_config: ObservabilityConfig) -> TestScenarios:
    """Test scenarios for triggering observability events."""
    return TestScenarios(obs_config)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def wait_for_scrape(scrape_interval: float = 15.0, buffer: float = 5.0) -> None:
    """
    Wait for Prometheus to scrape new metrics.
    
    Args:
        scrape_interval: Prometheus scrape interval in seconds
        buffer: Extra buffer time
    """
    time.sleep(scrape_interval + buffer)


async def async_wait_for_scrape(scrape_interval: float = 15.0, buffer: float = 5.0) -> None:
    """Async version of wait_for_scrape."""
    await asyncio.sleep(scrape_interval + buffer)


def verify_service_health(config: ObservabilityConfig) -> Dict[str, bool]:
    """
    Verify all observability services are healthy.
    
    Returns:
        Dict mapping service name to health status
    """
    results = {}
    
    with httpx.Client(timeout=10.0) as client:
        # Prometheus
        try:
            r = client.get(f"{config.prometheus_url}/-/healthy")
            results["prometheus"] = r.status_code == 200
        except Exception:
            results["prometheus"] = False
        
        # Grafana
        try:
            r = client.get(f"{config.grafana_url}/api/health")
            results["grafana"] = r.status_code == 200
        except Exception:
            results["grafana"] = False
        
        # OTEL Collector
        try:
            r = client.get(config.otel_collector_url)
            results["otel_collector"] = r.status_code == 200
        except Exception:
            results["otel_collector"] = False
        
        # Dashboard Service
        try:
            r = client.get(f"{config.dashboard_url}/health")
            results["dashboard"] = r.status_code == 200
        except Exception:
            results["dashboard"] = False
        
        # Orchestrator metrics
        try:
            r = client.get(f"{config.orchestrator_metrics}/metrics")
            results["orchestrator_metrics"] = r.status_code == 200
        except Exception:
            results["orchestrator_metrics"] = False
    
    return results


@pytest.fixture(scope="session")
def ensure_services_healthy(obs_config: ObservabilityConfig):
    """
    Fixture that ensures all observability services are healthy before tests run.
    
    Skips the test session if critical services are down.
    """
    health = verify_service_health(obs_config)
    
    critical_services = ["prometheus", "orchestrator_metrics"]
    for service in critical_services:
        if not health.get(service, False):
            pytest.skip(f"Critical service {service} is not healthy")
    
    return health
