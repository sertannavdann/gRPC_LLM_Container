"""
Dashboard Service - FastAPI Entry Point

HTTP API for accessing unified user context from all configured adapters.
Provides endpoints for:
- Full context retrieval
- Category-specific data
- Health checks
- Cache management
- Prometheus metrics (/metrics)
"""
import os
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .aggregator import DashboardAggregator, UserConfig
from shared.adapters import adapter_registry

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# OBSERVABILITY SETUP
# =============================================================================

def setup_observability() -> None:
    """Initialize OpenTelemetry tracing and metrics."""
    if os.getenv("ENABLE_OBSERVABILITY", "true").lower() != "true":
        logger.info("Observability disabled via ENABLE_OBSERVABILITY env var")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "dashboard-service")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    # Setup tracing
    tracer_provider = TracerProvider(resource=resource)
    try:
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        logger.info(f"Tracing configured with OTLP endpoint: {otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to configure OTLP tracing: {e}")

    # Setup metrics
    try:
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        logger.info(f"Metrics configured with OTLP endpoint: {otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to configure OTLP metrics: {e}")


# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

# Request metrics
DASHBOARD_REQUESTS = Counter(
    "dashboard_requests_total",
    "Total dashboard API requests",
    ["endpoint", "method", "status"]
)

DASHBOARD_REQUEST_DURATION = Histogram(
    "dashboard_request_duration_seconds",
    "Dashboard request duration in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Aggregator metrics
AGGREGATOR_FETCH_DURATION = Histogram(
    "dashboard_aggregator_fetch_seconds",
    "Time to fetch data from adapters",
    ["category"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

AGGREGATOR_CACHE_HITS = Counter(
    "dashboard_cache_hits_total",
    "Number of cache hits",
    ["category"]
)

AGGREGATOR_CACHE_MISSES = Counter(
    "dashboard_cache_misses_total",
    "Number of cache misses",
    ["category"]
)

# Context metrics
CONTEXT_ITEMS = Gauge(
    "dashboard_context_items",
    "Number of items in user context",
    ["user_id", "category", "relevance"]
)

ACTIVE_USERS = Gauge(
    "dashboard_active_users",
    "Number of active user aggregators"
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    adapters_registered: int


class RefreshRequest(BaseModel):
    """Request body for cache refresh."""
    user_id: Optional[str] = None
    categories: Optional[List[str]] = None


class RefreshResponse(BaseModel):
    """Response from cache refresh."""
    success: bool
    message: str
    user_id: Optional[str] = None


class AdapterInfo(BaseModel):
    """Information about a registered adapter."""
    category: str
    platform: str
    display_name: str
    requires_auth: bool


class AdaptersResponse(BaseModel):
    """Response listing available adapters."""
    categories: List[str]
    adapters: List[AdapterInfo]


# =============================================================================
# APPLICATION SETUP
# =============================================================================

# In-memory aggregator cache (per user)
_aggregators: dict[str, DashboardAggregator] = {}


def get_aggregator(user_id: str) -> DashboardAggregator:
    """Get or create an aggregator for a user."""
    if user_id not in _aggregators:
        # Default configuration - uses mock adapters
        config = UserConfig(
            user_id=user_id,
            finance=["mock"],
            calendar=["mock"],
            health=["mock"],
            navigation=["mock"],
        )
        _aggregators[user_id] = DashboardAggregator(
            user_config=config,
            cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "300"))
        )
    return _aggregators[user_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Dashboard Service starting up...")
    
    # Initialize observability
    setup_observability()
    
    logger.info(f"Registered adapters: {adapter_registry.to_dict()}")
    yield
    logger.info("Dashboard Service shutting down...")
    _aggregators.clear()


# Create FastAPI app
app = FastAPI(
    title="Dashboard Service",
    description="Unified context aggregator for user data from multiple platforms",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# METRICS MIDDLEWARE
# =============================================================================

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record request metrics for all endpoints."""
    start_time = time.time()
    
    # Skip metrics endpoint to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)
    
    response = await call_next(request)
    
    # Record metrics
    duration = time.time() - start_time
    endpoint = request.url.path
    
    DASHBOARD_REQUESTS.labels(
        endpoint=endpoint,
        method=request.method,
        status=response.status_code
    ).inc()
    
    DASHBOARD_REQUEST_DURATION.labels(endpoint=endpoint).observe(duration)
    
    # Update active users gauge
    ACTIVE_USERS.set(len(_aggregators))
    
    return response


# =============================================================================
# PROMETHEUS METRICS ENDPOINT
# =============================================================================

@app.get("/metrics", tags=["System"], include_in_schema=False)
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.
    
    Exposes all dashboard service metrics in Prometheus text format.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Returns service status and basic information.
    """
    adapters = adapter_registry.list_all_flat()
    return HealthResponse(
        status="healthy",
        service="dashboard-service",
        version="1.0.0",
        adapters_registered=len(adapters),
    )


@app.get("/context", tags=["Context"])
async def get_unified_context(
    user_id: str = Query(default="default", description="User identifier"),
    force_refresh: bool = Query(default=False, description="Bypass cache"),
):
    """
    Get unified context for a user.

    Aggregates data from all configured adapters (finance, calendar, health, navigation)
    into a single context object with relevance classification.
    """
    try:
        aggregator = get_aggregator(user_id)
        context = await aggregator.get_unified_context(force_refresh=force_refresh)
        return context.to_dict()
    except Exception as e:
        logger.error(f"Error fetching context for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/context/{category}", tags=["Context"])
async def get_category_context(
    category: str,
    user_id: str = Query(default="default", description="User identifier"),
    force_refresh: bool = Query(default=False, description="Bypass cache"),
):
    """
    Get context for a specific category.

    Categories: finance, calendar, health, navigation
    """
    valid_categories = ["finance", "calendar", "health", "navigation"]
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {category}. Valid: {valid_categories}"
        )

    try:
        aggregator = get_aggregator(user_id)
        data = await aggregator.get_category_data(
            category=category,
            force_refresh=force_refresh,
        )
        return {
            "category": category,
            "user_id": user_id,
            "data": data,
        }
    except Exception as e:
        logger.error(f"Error fetching {category} for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/refresh", response_model=RefreshResponse, tags=["Cache"])
async def force_refresh(request: RefreshRequest):
    """
    Force cache refresh for a user.

    Clears cached data and triggers a fresh fetch from all adapters.
    """
    user_id = request.user_id or "default"

    try:
        aggregator = get_aggregator(user_id)
        aggregator.clear_cache(user_id)

        # Optionally trigger immediate refresh
        if request.categories:
            await aggregator.get_unified_context(
                force_refresh=True,
                categories=request.categories,
            )
        else:
            await aggregator.get_unified_context(force_refresh=True)

        return RefreshResponse(
            success=True,
            message="Cache cleared and data refreshed",
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"Error refreshing cache for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adapters", response_model=AdaptersResponse, tags=["System"])
async def list_adapters():
    """
    List all registered adapters.

    Returns available adapters grouped by category.
    """
    registry_data = adapter_registry.to_dict()

    adapters = []
    for category, adapter_list in registry_data.get("adapters", {}).items():
        for adapter in adapter_list:
            adapters.append(AdapterInfo(
                category=category,
                platform=adapter["platform"],
                display_name=adapter["display_name"],
                requires_auth=adapter["requires_auth"],
            ))

    return AdaptersResponse(
        categories=registry_data.get("categories", []),
        adapters=adapters,
    )


@app.get("/relevance/{user_id}", tags=["Context"])
async def get_relevance_summary(
    user_id: str,
    force_refresh: bool = Query(default=False, description="Bypass cache"),
):
    """
    Get relevance-classified data for a user.

    Returns items classified as HIGH, MEDIUM, or LOW relevance
    based on urgency and actionability.
    """
    try:
        aggregator = get_aggregator(user_id)
        context = await aggregator.get_unified_context(force_refresh=force_refresh)

        return {
            "user_id": user_id,
            "relevance": context.relevance,
            "high_count": len(context.relevance.get("high", [])),
            "medium_count": len(context.relevance.get("medium", [])),
            "low_count": len(context.relevance.get("low", [])),
        }
    except Exception as e:
        logger.error(f"Error fetching relevance for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts/{user_id}", tags=["Context"])
async def get_alerts(
    user_id: str,
    force_refresh: bool = Query(default=False, description="Bypass cache"),
):
    """
    Get high-priority alerts for a user.

    Returns only HIGH relevance items that have associated alerts.
    """
    try:
        aggregator = get_aggregator(user_id)
        alerts = aggregator.relevance_engine.get_high_priority_alerts(
            await aggregator.get_unified_context(force_refresh=force_refresh)
        )

        return {
            "user_id": user_id,
            "alerts": alerts,
            "count": len(alerts),
        }
    except Exception as e:
        logger.error(f"Error fetching alerts for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    uvicorn.run(
        "dashboard_service.main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
