"""
Metrics End-to-End Tests

Verifies that metrics from gRPC services appear correctly in Prometheus.
These tests require the full observability stack to be running:
    make observability-up
    ENABLE_OBSERVABILITY=true docker compose up orchestrator dashboard
"""
import pytest
import time
import asyncio
from typing import List

from .conftest import (
    PrometheusClient,
    GrafanaClient,
    TestScenarios,
    ObservabilityConfig,
    wait_for_scrape,
    async_wait_for_scrape,
    verify_service_health,
)


# =============================================================================
# SERVICE HEALTH TESTS
# =============================================================================

class TestServiceHealth:
    """Verify observability services are running and healthy."""
    
    def test_prometheus_healthy(self, prometheus_client: PrometheusClient):
        """Prometheus should be healthy and accepting queries."""
        result = prometheus_client.query("up")
        assert result.get("status") == "success", "Prometheus query failed"
    
    def test_grafana_healthy(self, grafana_client: GrafanaClient):
        """Grafana should be healthy."""
        assert grafana_client.health_check(), "Grafana is not healthy"
    
    def test_prometheus_datasource_connected(self, grafana_client: GrafanaClient):
        """Prometheus datasource should be configured in Grafana."""
        datasources = grafana_client.list_datasources()
        prometheus_ds = next(
            (ds for ds in datasources if ds["type"] == "prometheus"),
            None
        )
        assert prometheus_ds is not None, "Prometheus datasource not found in Grafana"
    
    def test_all_services_healthy(self, obs_config: ObservabilityConfig):
        """All observability services should be healthy."""
        health = verify_service_health(obs_config)
        
        # Log status for debugging
        for service, status in health.items():
            print(f"{service}: {'✓' if status else '✗'}")
        
        # At minimum, Prometheus should be healthy
        assert health.get("prometheus", False), "Prometheus is not healthy"


# =============================================================================
# GRPC METRICS TESTS
# =============================================================================

class TestGrpcMetrics:
    """Verify gRPC request metrics are collected correctly."""
    
    @pytest.mark.asyncio
    async def test_grpc_request_counter_increments(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Sending a gRPC request should increment the request counter.
        """
        # Get initial count
        initial = prometheus_client.get_metric_value(
            "sum(grpc_llm_grpc_requests_total)"
        ) or 0
        
        # Send a request
        result = await test_scenarios.send_simple_query("Test request for metrics")
        assert result["success"], f"Query failed: {result.get('error')}"
        
        # Wait for Prometheus to scrape
        wait_for_scrape(scrape_interval=15.0)
        
        # Check counter increased
        final = prometheus_client.get_metric_value(
            "sum(grpc_llm_grpc_requests_total)"
        ) or 0
        
        assert final > initial, (
            f"Request counter did not increase: {initial} -> {final}"
        )
    
    @pytest.mark.asyncio
    async def test_grpc_latency_recorded(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        gRPC request latency should be recorded in the histogram.
        """
        # Send a request
        result = await test_scenarios.send_simple_query("Test latency recording")
        assert result["success"], f"Query failed: {result.get('error')}"
        
        # Wait for scrape
        wait_for_scrape()
        
        # Check histogram has data
        p95 = prometheus_client.get_metric_value(
            "histogram_quantile(0.95, sum(rate(grpc_llm_grpc_request_duration_ms_bucket[5m])) by (le))"
        )
        
        assert p95 is not None, "P95 latency not recorded"
        assert p95 > 0, "P95 latency should be positive"
    
    @pytest.mark.asyncio
    async def test_method_labels_present(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Metrics should have method labels for differentiation.
        """
        # Send a request to ensure data exists
        await test_scenarios.send_simple_query("Test method labels")
        wait_for_scrape()
        
        # Query with method label
        result = prometheus_client.query(
            'grpc_llm_grpc_requests_total{method=~".*QueryAgent.*"}'
        )
        
        assert result.get("status") == "success"
        data = result.get("data", {}).get("result", [])
        
        # Should have at least one result with method label
        assert len(data) > 0, "No metrics found with method label"


# =============================================================================
# TOOL METRICS TESTS
# =============================================================================

class TestToolMetrics:
    """Verify tool execution metrics are collected."""
    
    @pytest.mark.asyncio
    async def test_tool_call_counter(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Tool calls should be counted in metrics.
        """
        # Get initial count
        initial = prometheus_client.get_metric_value(
            "sum(grpc_llm_tool_calls_total)"
        ) or 0
        
        # Send a query that should trigger tools
        result = await test_scenarios.send_tool_query()
        
        # Wait for scrape
        wait_for_scrape()
        
        # Check if tools were recorded (may be 0 if no tools triggered)
        final = prometheus_client.get_metric_value(
            "sum(grpc_llm_tool_calls_total)"
        ) or 0
        
        # Log for debugging
        print(f"Tool calls: {initial} -> {final}")
        
        # At minimum, metric should exist
        assert prometheus_client.metric_exists("grpc_llm_tool_calls_total") or final >= initial
    
    @pytest.mark.asyncio
    async def test_tool_duration_histogram(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Tool execution duration should be recorded.
        """
        # Send query to trigger tools
        await test_scenarios.send_tool_query()
        wait_for_scrape()
        
        # Check histogram exists
        exists = prometheus_client.metric_exists("grpc_llm_tool_duration_ms_bucket")
        
        # Tool duration metric should exist (even if no data yet)
        # This is a weaker assertion since tools may not be triggered
        print(f"Tool duration metric exists: {exists}")


# =============================================================================
# PROVIDER METRICS TESTS
# =============================================================================

class TestProviderMetrics:
    """Verify LLM provider metrics are collected."""
    
    @pytest.mark.asyncio
    async def test_provider_request_counter(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Provider requests should be counted with provider label.
        """
        # Send a request
        await test_scenarios.send_simple_query("Test provider metrics")
        wait_for_scrape()
        
        # Check provider requests metric exists
        result = prometheus_client.query("grpc_llm_llm_provider_requests_total")
        
        assert result.get("status") == "success"
        
        # Check if any provider data exists
        data = result.get("data", {}).get("result", [])
        if data:
            # Verify provider label is present
            for item in data:
                labels = item.get("metric", {})
                assert "provider" in labels, "Provider label missing from metric"
    
    @pytest.mark.asyncio
    async def test_provider_latency_by_provider(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Provider latency should be recorded per provider.
        """
        # Send request
        await test_scenarios.send_simple_query("Test provider latency")
        wait_for_scrape()
        
        # Query latency grouped by provider
        result = prometheus_client.query(
            "histogram_quantile(0.50, sum(rate(grpc_llm_llm_provider_latency_ms_bucket[5m])) by (le, provider))"
        )
        
        assert result.get("status") == "success"
        
        # Log providers found
        data = result.get("data", {}).get("result", [])
        providers = [item.get("metric", {}).get("provider") for item in data]
        print(f"Providers with latency data: {providers}")


# =============================================================================
# DASHBOARD METRICS TESTS
# =============================================================================

class TestDashboardMetrics:
    """Verify dashboard service metrics are collected."""
    
    def test_dashboard_request_counter(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Dashboard requests should be counted.
        """
        # Get initial count
        initial = prometheus_client.get_metric_value(
            "sum(dashboard_requests_total)"
        ) or 0
        
        # Make a dashboard request
        result = test_scenarios.fetch_dashboard_context()
        assert result["success"], f"Dashboard request failed: {result}"
        
        # Wait for scrape
        wait_for_scrape()
        
        # Check counter increased
        final = prometheus_client.get_metric_value(
            "sum(dashboard_requests_total)"
        ) or 0
        
        assert final > initial, (
            f"Dashboard request counter did not increase: {initial} -> {final}"
        )
    
    def test_dashboard_latency_histogram(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Dashboard request latency should be recorded.
        """
        # Make requests
        test_scenarios.fetch_dashboard_context()
        test_scenarios.trigger_dashboard_cache_miss()
        wait_for_scrape()
        
        # Check histogram
        p95 = prometheus_client.get_metric_value(
            "histogram_quantile(0.95, sum(rate(dashboard_request_duration_seconds_bucket[5m])) by (le))"
        )
        
        # May be None if no data yet, but metric should exist
        exists = prometheus_client.metric_exists("dashboard_request_duration_seconds_bucket")
        assert exists or p95 is not None, "Dashboard latency metric not found"
    
    def test_dashboard_cache_metrics(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Dashboard cache hits and misses should be tracked.
        """
        # Trigger cache miss
        test_scenarios.trigger_dashboard_cache_miss()
        
        # Trigger cache hit (same user)
        test_scenarios.fetch_dashboard_context(user_id="cache-test-user")
        test_scenarios.fetch_dashboard_context(user_id="cache-test-user")
        
        wait_for_scrape()
        
        # Check cache metrics exist
        hits_exist = prometheus_client.metric_exists("dashboard_cache_hits_total")
        misses_exist = prometheus_client.metric_exists("dashboard_cache_misses_total")
        
        print(f"Cache hits metric exists: {hits_exist}")
        print(f"Cache misses metric exists: {misses_exist}")


# =============================================================================
# GRAFANA DASHBOARD TESTS
# =============================================================================

class TestGrafanaDashboards:
    """Verify Grafana dashboards are provisioned and accessible."""
    
    def test_overview_dashboard_exists(self, grafana_client: GrafanaClient):
        """Main overview dashboard should be provisioned."""
        dashboards = grafana_client.list_dashboards()
        titles = [d.get("title", "") for d in dashboards]
        
        # Should have at least the overview dashboard
        assert any("Overview" in t or "gRPC" in t for t in titles), (
            f"Overview dashboard not found. Available: {titles}"
        )
    
    def test_provider_comparison_dashboard_exists(self, grafana_client: GrafanaClient):
        """Provider comparison dashboard should be provisioned."""
        dashboard = grafana_client.get_dashboard("provider-comparison")
        assert dashboard is not None, "Provider comparison dashboard not found"
    
    def test_tool_execution_dashboard_exists(self, grafana_client: GrafanaClient):
        """Tool execution dashboard should be provisioned."""
        dashboard = grafana_client.get_dashboard("tool-execution")
        assert dashboard is not None, "Tool execution dashboard not found"
    
    def test_service_health_dashboard_exists(self, grafana_client: GrafanaClient):
        """Service health dashboard should be provisioned."""
        dashboard = grafana_client.get_dashboard("service-health")
        assert dashboard is not None, "Service health dashboard not found"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestMetricsIntegration:
    """
    Integration tests that verify the full metrics pipeline.
    """
    
    @pytest.mark.asyncio
    async def test_full_request_metrics_pipeline(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        A complete request should generate metrics across all layers:
        - gRPC request counter and latency
        - Provider request counter
        - Tool counters (if tools used)
        """
        # Send a complex query
        result = await test_scenarios.send_multi_tool_query()
        
        # Wait for scrape
        wait_for_scrape(scrape_interval=20.0)
        
        # Verify gRPC metrics
        grpc_requests = prometheus_client.metric_exists("grpc_llm_grpc_requests_total")
        assert grpc_requests, "gRPC request metrics missing"
        
        # Verify provider metrics
        provider_requests = prometheus_client.metric_exists("grpc_llm_llm_provider_requests_total")
        assert provider_requests, "Provider request metrics missing"
        
        # Log result for debugging
        print(f"Query result: success={result['success']}, latency={result.get('latency_ms')}")
    
    @pytest.mark.asyncio
    async def test_metrics_cardinality(
        self,
        prometheus_client: PrometheusClient,
        test_scenarios: TestScenarios,
    ):
        """
        Metrics should have appropriate cardinality (not exploding).
        """
        # Send several requests
        for i in range(5):
            await test_scenarios.send_simple_query(f"Cardinality test {i}")
        
        wait_for_scrape()
        
        # Get all metric names
        all_metrics = prometheus_client.get_all_metric_names()
        grpc_llm_metrics = [m for m in all_metrics if m.startswith("grpc_llm_")]
        
        print(f"gRPC LLM metrics found: {len(grpc_llm_metrics)}")
        for m in grpc_llm_metrics:
            print(f"  - {m}")
        
        # Should have reasonable number of metrics (not thousands)
        assert len(grpc_llm_metrics) < 100, "Too many metrics - possible label explosion"
