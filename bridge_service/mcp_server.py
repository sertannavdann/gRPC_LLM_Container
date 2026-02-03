"""
MCP (Model Context Protocol) Server - Bridge between OpenClaw and gRPC Microservices

This server exposes your gRPC microservices as MCP tools that OpenClaw can invoke.
It provides bidirectional communication:
  - OpenClaw → gRPC services (tool invocation)
  - gRPC services → OpenClaw (context/response routing)

Exposed Tools:
  - query_agent: Send queries to the orchestrator
  - get_context: Fetch aggregated context from dashboard
  - search_knowledge: Query ChromaDB for semantic search
  - execute_code: Run code in sandbox
  - get_daily_briefing: Morning summary
  - plan_day: Time-blocked schedule
  - list_tools: List all available tools
  - get_service_health: Check microservices health

Features:
  - Pydantic input validation
  - Rate limiting per tool
  - Context caching (5 min TTL)
  - gRPC connection pooling
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import grpc
from aiohttp import web
import aiohttp
from pydantic import BaseModel, Field, field_validator
from aiolimiter import AsyncLimiter
from cachetools import TTLCache

# Import gRPC generated stubs
import sys
sys.path.insert(0, '/app')

from shared.generated import agent_pb2, agent_pb2_grpc
from shared.generated import chroma_pb2, chroma_pb2_grpc
from shared.generated import sandbox_pb2, sandbox_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Input Validation
# =============================================================================

class QueryCategory(str, Enum):
    COMMUTE = "commute"
    CALENDAR = "calendar"
    WEATHER = "weather"
    GENERAL = "general"
    FINANCE = "finance"
    HEALTH = "health"


class ContextSection(str, Enum):
    CALENDAR = "calendar"
    ACTIVITY = "activity"
    PREFERENCES = "preferences"
    HEALTH = "health"
    FINANCE = "finance"


class TimeRange(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"


class KnowledgeCollection(str, Enum):
    DEFAULT = "default"
    NOTES = "notes"
    DOCUMENTS = "documents"
    BOOKMARKS = "bookmarks"
    CONVERSATIONS = "conversations"


class QueryAgentArgs(BaseModel):
    """Validated arguments for query_agent tool."""
    query: str = Field(..., min_length=1, max_length=10000, description="Natural language query")
    category: Optional[QueryCategory] = Field(None, description="Query category hint")
    debug: bool = Field(False, description="Enable debug trace")

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Query cannot be empty or whitespace')
        return v.strip()


class GetContextArgs(BaseModel):
    """Validated arguments for get_context tool."""
    user_id: str = Field("default", description="User identifier")
    sections: Optional[List[ContextSection]] = Field(None, description="Sections to include")
    time_range: TimeRange = Field(TimeRange.TODAY, description="Time range")


class SearchKnowledgeArgs(BaseModel):
    """Validated arguments for search_knowledge tool."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    collection: KnowledgeCollection = Field(KnowledgeCollection.DEFAULT, description="Collection")
    top_k: int = Field(5, ge=1, le=20, description="Number of results")
    filter_date_after: Optional[str] = Field(None, description="Date filter (ISO format)")


class ExecuteCodeArgs(BaseModel):
    """Validated arguments for execute_code tool."""
    code: str = Field(..., min_length=1, max_length=50000, description="Python code")
    timeout: int = Field(30, ge=1, le=60, description="Timeout in seconds")


class DailyBriefingArgs(BaseModel):
    """Validated arguments for get_daily_briefing tool."""
    include_weather: bool = Field(True, description="Include weather")
    include_commute: bool = Field(True, description="Include commute info")


class PlanDayArgs(BaseModel):
    """Validated arguments for plan_day tool."""
    work_start: str = Field("09:00", pattern=r"^\d{2}:\d{2}$", description="Start time HH:MM")
    work_end: str = Field("18:00", pattern=r"^\d{2}:\d{2}$", description="End time HH:MM")
    include_breaks: bool = Field(True, description="Include break times")
    priorities: List[str] = Field(default_factory=list, description="Priority tasks")


# =============================================================================
# MCP Tool Definition
# =============================================================================

@dataclass
class MCPToolDefinition:
    """MCP Tool definition following the protocol spec."""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPServerConfig:
    """Configuration for the MCP server."""
    host: str = "0.0.0.0"
    port: int = 8100
    orchestrator_addr: str = "orchestrator:50054"
    chroma_addr: str = "chroma_service:50052"
    sandbox_addr: str = "sandbox_service:50057"
    dashboard_url: str = "http://dashboard:8001"
    openclaw_url: str = "http://host.docker.internal:18789"


class GRPCBridge:
    """Bridge to gRPC microservices."""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._channels: Dict[str, grpc.aio.Channel] = {}
    
    async def get_orchestrator_stub(self) -> agent_pb2_grpc.AgentServiceStub:
        """Get or create orchestrator stub."""
        if "orchestrator" not in self._channels:
            self._channels["orchestrator"] = grpc.aio.insecure_channel(
                self.config.orchestrator_addr
            )
        return agent_pb2_grpc.AgentServiceStub(self._channels["orchestrator"])
    
    async def get_chroma_stub(self) -> chroma_pb2_grpc.ChromaServiceStub:
        """Get or create chroma stub."""
        if "chroma" not in self._channels:
            self._channels["chroma"] = grpc.aio.insecure_channel(
                self.config.chroma_addr
            )
        return chroma_pb2_grpc.ChromaServiceStub(self._channels["chroma"])
    
    async def get_sandbox_stub(self) -> sandbox_pb2_grpc.SandboxServiceStub:
        """Get or create sandbox stub."""
        if "sandbox" not in self._channels:
            self._channels["sandbox"] = grpc.aio.insecure_channel(
                self.config.sandbox_addr
            )
        return sandbox_pb2_grpc.SandboxServiceStub(self._channels["sandbox"])
    
    async def close(self):
        """Close all channels."""
        for channel in self._channels.values():
            await channel.close()


class MCPServer:
    """
    MCP Server that exposes gRPC microservices as tools.
    
    Implements the Model Context Protocol for tool invocation.
    Features:
    - Pydantic input validation
    - Rate limiting per tool (prevents abuse)
    - Context caching (reduces redundant calls)
    - gRPC connection pooling
    """
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.bridge = GRPCBridge(config)
        self.app = web.Application()
        self._setup_routes()
        self._tools = self._define_tools()
        
        # Rate limiters per tool (requests per minute)
        self._rate_limiters: Dict[str, AsyncLimiter] = {
            "execute_code": AsyncLimiter(10, 60),      # 10 calls/minute (expensive)
            "query_agent": AsyncLimiter(30, 60),       # 30 calls/minute
            "search_knowledge": AsyncLimiter(60, 60),  # 60 calls/minute
            "get_daily_briefing": AsyncLimiter(5, 60), # 5 calls/minute (aggregates multiple)
            "plan_day": AsyncLimiter(5, 60),           # 5 calls/minute
        }
        
        # Cache for expensive operations (TTL in seconds)
        self._context_cache: TTLCache = TTLCache(maxsize=100, ttl=300)  # 5 min
        self._health_cache: TTLCache = TTLCache(maxsize=10, ttl=30)     # 30 sec
        
        # Tool usage metrics
        self._tool_calls: Dict[str, int] = {}
        self._tool_errors: Dict[str, int] = {}
    
    def _setup_routes(self):
        """Setup HTTP routes for MCP protocol."""
        # MCP Protocol endpoints
        self.app.router.add_get("/", self.handle_info)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/tools", self.handle_list_tools)
        self.app.router.add_post("/tools/{tool_name}", self.handle_invoke_tool)
        
        # Metrics endpoint
        self.app.router.add_get("/metrics", self.handle_metrics)

        # SSE endpoint for streaming (MCP spec)
        self.app.router.add_get("/sse", self.handle_sse)
        
        # JSON-RPC endpoint (alternative MCP transport)
        self.app.router.add_post("/rpc", self.handle_jsonrpc)
    
    def _define_tools(self) -> Dict[str, MCPToolDefinition]:
        """Define available tools following MCP schema."""
        return {
            "query_agent": MCPToolDefinition(
                name="query_agent",
                description="""Send a natural language query to the AI agent orchestrator.

USE THIS TOOL WHEN:
- User asks about commute times, traffic, or directions to a location
- User wants calendar information, meetings, or scheduling
- User asks about weather conditions
- User needs general information that requires reasoning over multiple data sources
- User asks complex questions that may need web search or calculation

DO NOT USE WHEN:
- You just need to search the knowledge base (use search_knowledge instead)
- You need to run specific code (use execute_code instead)
- You need a quick context summary (use get_context instead)

The agent will automatically select and chain appropriate tools.""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The natural language query. Be specific - include locations, dates, times when relevant."
                        },
                        "category": {
                            "type": "string",
                            "enum": ["commute", "calendar", "weather", "general", "finance", "health"],
                            "description": "Optional hint about query category to improve routing"
                        },
                        "debug": {
                            "type": "boolean",
                            "description": "Enable debug mode for detailed execution trace",
                            "default": False
                        }
                    },
                    "required": ["query"]
                }
            ),
            "get_context": MCPToolDefinition(
                name="get_context",
                description="""Fetch the user's current aggregated context including calendar, activity, and preferences.

USE THIS TOOL WHEN:
- User asks "what's my context?" or "what do you know about me?"
- You need background information before answering a personalized question
- User asks about their schedule, recent activity, or preferences
- Starting a conversation and need to ground responses in user data

RETURNS:
- Calendar: Upcoming events, meetings, reminders
- Activity: Recent interactions, queries, patterns
- Preferences: User settings, common destinations, habits
- Health: Recent health metrics if available
- Finance: Budget status, recent transactions if available""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to fetch context for",
                            "default": "default"
                        },
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["calendar", "activity", "preferences", "health", "finance"]
                            },
                            "description": "Specific sections to include. Omit for all sections."
                        },
                        "time_range": {
                            "type": "string",
                            "enum": ["today", "week", "month"],
                            "description": "Time range for activity and calendar",
                            "default": "today"
                        }
                    }
                }
            ),
            "search_knowledge": MCPToolDefinition(
                name="search_knowledge",
                description="""Semantic search across the user's personal knowledge base (notes, documents, saved content).

USE THIS TOOL WHEN:
- User asks to find notes, documents, or saved information
- User mentions "I wrote about...", "I saved...", "find my notes on..."
- Looking for specific topics in the user's personal knowledge
- User asks about past research, bookmarks, or references
- Need to retrieve relevant context from stored documents

EXAMPLES:
- "Find my notes on habit formation" → query="habit formation routines behavior change"
- "What did I save about Python decorators?" → query="Python decorators functions"
- "Search for meeting notes from project X" → query="project X meeting notes decisions"

TIP: Use descriptive multi-word queries for better semantic matching.""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Semantic search query. Use natural language, include synonyms and related terms for better results."
                        },
                        "collection": {
                            "type": "string",
                            "enum": ["default", "notes", "documents", "bookmarks", "conversations"],
                            "description": "Knowledge collection to search",
                            "default": "default"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (1-20)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        },
                        "filter_date_after": {
                            "type": "string",
                            "description": "Only return documents created after this date (ISO format)"
                        }
                    },
                    "required": ["query"]
                }
            ),
            "execute_code": MCPToolDefinition(
                name="execute_code",
                description="""Execute Python code in a secure sandboxed environment.

USE THIS TOOL WHEN:
- User asks to run, execute, or test Python code
- Need to perform calculations, data transformations, or analysis
- User wants to validate code snippets
- Need to process data and return computed results

SANDBOX LIMITATIONS:
- No network access (no requests, urllib, etc.)
- No filesystem writes outside /tmp
- Limited to 256MB memory
- Standard library + numpy, pandas, json available
- Max execution time enforced by timeout

SECURITY: Code runs in isolated container. Safe to execute user-provided code.

TIP: Always print() results you want to return - stdout is captured.""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute. Use print() to output results."
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Max execution time in seconds (1-60)",
                            "default": 30,
                            "minimum": 1,
                            "maximum": 60
                        }
                    },
                    "required": ["code"]
                }
            ),
            "list_available_tools": MCPToolDefinition(
                name="list_available_tools",
                description="""List all tools available in the agent's tool registry.

USE THIS TOOL WHEN:
- User asks "what can you do?" or "what tools do you have?"
- Need to check if a specific capability is available
- Debugging or exploring system capabilities

NOTE: This is a system/diagnostic tool. For most user queries, use query_agent instead.""",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            "get_service_health": MCPToolDefinition(
                name="get_service_health",
                description="""Check health status of all backend microservices.

USE THIS TOOL WHEN:
- User types /infra or /status
- User asks about system health or service status
- Diagnosing connectivity issues
- Checking if services are available before making calls

RETURNS: Health status for orchestrator, ChromaDB, sandbox, and dashboard services.""",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            "get_daily_briefing": MCPToolDefinition(
                name="get_daily_briefing",
                description="""Generate a personalized daily briefing summarizing calendar, tasks, and relevant context.

USE THIS TOOL WHEN:
- User asks for a "daily briefing", "morning summary", or "what's my day look like?"
- User wants an overview of their schedule and priorities
- Starting the day and need a quick status update

RETURNS: Structured summary including:
- Today's calendar events and meetings
- Priority tasks and deadlines
- Weather summary (if relevant)
- Recent activity highlights
- Any alerts or reminders""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_weather": {
                            "type": "boolean",
                            "description": "Include weather forecast",
                            "default": True
                        },
                        "include_commute": {
                            "type": "boolean",
                            "description": "Include commute time to first meeting",
                            "default": True
                        }
                    }
                }
            ),
            "plan_day": MCPToolDefinition(
                name="plan_day",
                description="""Generate a time-blocked schedule for the day based on calendar and tasks.

USE THIS TOOL WHEN:
- User asks to "plan my day" or "create a schedule"
- User wants help organizing their time
- User has meetings and tasks and wants them arranged optimally

RETURNS: Time-blocked schedule with:
- Fixed events (meetings, appointments)
- Suggested time blocks for tasks
- Break recommendations
- Buffer time for commutes

TIP: Works best when calendar and task data is available in the context.""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "work_start": {
                            "type": "string",
                            "description": "Work day start time (HH:MM format)",
                            "default": "09:00"
                        },
                        "work_end": {
                            "type": "string",
                            "description": "Work day end time (HH:MM format)",
                            "default": "18:00"
                        },
                        "include_breaks": {
                            "type": "boolean",
                            "description": "Include suggested break times",
                            "default": True
                        },
                        "priorities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of priority tasks to schedule first"
                        }
                    }
                }
            )
        }
    
    # =========================================================================
    # HTTP Handlers
    # =========================================================================
    
    async def handle_info(self, request: web.Request) -> web.Response:
        """Return server info."""
        return web.json_response({
            "name": "grpc-llm-mcp-bridge",
            "version": "1.0.0",
            "description": "MCP server bridging OpenClaw to gRPC microservices",
            "protocol": "mcp",
            "capabilities": {
                "tools": True,
                "resources": False,
                "prompts": False
            }
        })
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})
    
    async def handle_list_tools(self, request: web.Request) -> web.Response:
        """List all available tools (MCP tools/list)."""
        tools_list = []
        for tool in self._tools.values():
            tools_list.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema
            })
        return web.json_response({"tools": tools_list})
    
    async def handle_invoke_tool(self, request: web.Request) -> web.Response:
        """Invoke a specific tool (MCP tools/call)."""
        tool_name = request.match_info["tool_name"]
        
        if tool_name not in self._tools:
            return web.json_response(
                {"error": f"Unknown tool: {tool_name}"},
                status=404
            )
        
        try:
            body = await request.json()
            arguments = body.get("arguments", {})
            result = await self._execute_tool(tool_name, arguments)
            return web.json_response({
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            })
        except Exception as e:
            logger.exception(f"Tool execution error: {tool_name}")
            return web.json_response({
                "content": [{"type": "text", "text": str(e)}],
                "isError": True
            }, status=500)
    
    async def handle_sse(self, request: web.Request) -> web.StreamResponse:
        """Server-Sent Events endpoint for streaming."""
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        await response.prepare(request)
        
        # Send initial connection message
        await response.write(b"event: connected\ndata: {\"status\": \"connected\"}\n\n")
        
        # Keep connection alive
        try:
            while True:
                await asyncio.sleep(30)
                await response.write(b": keepalive\n\n")
        except asyncio.CancelledError:
            pass
        
        return response
    
    async def handle_jsonrpc(self, request: web.Request) -> web.Response:
        """JSON-RPC 2.0 endpoint for MCP."""
        try:
            body = await request.json()
            method = body.get("method")
            params = body.get("params", {})
            req_id = body.get("id")
            
            if method == "tools/list":
                result = {"tools": [
                    {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                    for t in self._tools.values()
                ]}
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                tool_result = await self._execute_tool(tool_name, arguments)
                result = {
                    "content": [{"type": "text", "text": json.dumps(tool_result, indent=2)}],
                    "isError": False
                }
            elif method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "grpc-llm-mcp-bridge", "version": "1.0.0"},
                    "capabilities": {"tools": {}}
                }
            else:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                    "id": req_id
                })
            
            return web.json_response({
                "jsonrpc": "2.0",
                "result": result,
                "id": req_id
            })
        except Exception as e:
            logger.exception("JSON-RPC error")
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": body.get("id") if "body" in dir() else None
            }, status=500)
    
    # =========================================================================
    # Tool Execution with Rate Limiting and Validation
    # =========================================================================
    
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool with rate limiting and input validation."""
        handlers = {
            "query_agent": self._tool_query_agent,
            "get_context": self._tool_get_context,
            "search_knowledge": self._tool_search_knowledge,
            "execute_code": self._tool_execute_code,
            "list_available_tools": self._tool_list_tools,
            "get_service_health": self._tool_service_health,
            "get_daily_briefing": self._tool_daily_briefing,
            "plan_day": self._tool_plan_day,
        }
        
        # Pydantic validators per tool
        validators = {
            "query_agent": QueryAgentArgs,
            "get_context": GetContextArgs,
            "search_knowledge": SearchKnowledgeArgs,
            "execute_code": ExecuteCodeArgs,
            "get_daily_briefing": DailyBriefingArgs,
            "plan_day": PlanDayArgs,
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"No handler for tool: {tool_name}")
        
        # Track metrics
        self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1
        
        # Apply rate limiting if configured
        limiter = self._rate_limiters.get(tool_name)
        if limiter:
            try:
                async with limiter:
                    pass  # Acquire rate limit slot
            except Exception:
                logger.warning(f"Rate limit exceeded for tool: {tool_name}")
                return {"error": f"Rate limit exceeded for {tool_name}. Please try again shortly."}
        
        # Validate input with Pydantic if validator exists
        validator = validators.get(tool_name)
        if validator:
            try:
                validated = validator(**arguments)
                arguments = validated.model_dump()
            except Exception as e:
                self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1
                logger.warning(f"Validation error for {tool_name}: {e}")
                return {"error": f"Invalid arguments: {str(e)}"}
        
        try:
            return await handler(arguments)
        except Exception as e:
            self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1
            logger.exception(f"Tool execution error: {tool_name}")
            return {"error": f"Tool execution failed: {str(e)}"}
    
    async def handle_metrics(self, request: web.Request) -> web.Response:
        """Return tool usage metrics."""
        return web.json_response({
            "tool_calls": self._tool_calls,
            "tool_errors": self._tool_errors,
            "cache_stats": {
                "context_cache_size": len(self._context_cache),
                "health_cache_size": len(self._health_cache),
            },
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def _tool_query_agent(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Query the orchestrator agent."""
        query = args.get("query", "")
        debug = args.get("debug", False)
        category = args.get("category")
        
        stub = await self.bridge.get_orchestrator_stub()
        request = agent_pb2.AgentRequest(  # type: ignore[attr-defined]
            user_query=query,
            debug_mode=debug
        )
        
        try:
            logger.info(f"Querying agent: {query[:100]}... (category={category})")
            response = await stub.QueryAgent(request, timeout=120.0)
            return {
                "answer": response.final_answer,
                "context_used": response.context_used,
                "sources": response.sources,
                "execution_graph": response.execution_graph if debug else None
            }
        except grpc.RpcError as e:
            return {"error": f"gRPC error: {e.code()} - {e.details()}"}
    
    async def _tool_get_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch context from dashboard service with caching."""
        user_id = args.get("user_id", "default")
        sections = args.get("sections")
        time_range = args.get("time_range", "today")
        
        # Check cache first
        cache_key = f"context:{user_id}:{time_range}:{sections}"
        if cache_key in self._context_cache:
            logger.debug(f"Cache hit for context: {cache_key}")
            return self._context_cache[cache_key]
        
        # Build params - handle enum values
        params = {
            "user_id": user_id,
            "time_range": time_range.value if hasattr(time_range, 'value') else time_range,
        }
        if sections:
            params["sections"] = ",".join(s.value if hasattr(s, 'value') else s for s in sections)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.config.dashboard_url}/context",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # Cache the result
                        self._context_cache[cache_key] = result
                        return result
                    else:
                        return {"error": f"Dashboard returned {resp.status}"}
            except Exception as e:
                return {"error": f"Failed to fetch context: {e}"}
    
    async def _tool_search_knowledge(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search ChromaDB knowledge base."""
        query = args.get("query", "")
        collection = args.get("collection", "default")
        top_k = args.get("top_k", 5)
        
        # Handle enum values
        if hasattr(collection, 'value'):
            collection = collection.value
        
        stub = await self.bridge.get_chroma_stub()
        # Note: Current proto only has query_text and top_k
        request = chroma_pb2.QueryRequest(  # type: ignore[attr-defined]
            query_text=query,
            top_k=top_k
        )
        
        try:
            response = await stub.Query(request, timeout=30.0)
            results = []
            for doc in response.results:
                # Convert protobuf Struct to dict safely
                metadata = {}
                if doc.metadata and doc.metadata.fields:
                    from google.protobuf.json_format import MessageToDict
                    metadata = MessageToDict(doc.metadata)
                
                results.append({
                    "id": doc.id,
                    "text": doc.text,
                    "score": doc.score,
                    "metadata": metadata
                })
            return {"results": results, "count": len(results), "collection": collection}
        except grpc.RpcError as e:
            return {"error": f"ChromaDB error: {e.code()} - {e.details()}"}
    
    async def _tool_execute_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code in sandbox."""
        code = args.get("code", "")
        timeout = args.get("timeout", 30)
        
        stub = await self.bridge.get_sandbox_stub()
        request = sandbox_pb2.ExecuteCodeRequest(  # type: ignore[attr-defined]
            code=code,
            language="python",
            timeout_seconds=timeout
        )
        
        try:
            response = await stub.ExecuteCode(request, timeout=float(timeout + 5))
            return {
                "stdout": response.stdout,
                "stderr": response.stderr,
                "exit_code": response.exit_code,
                "execution_time_ms": response.execution_time_ms
            }
        except grpc.RpcError as e:
            return {"error": f"Sandbox error: {e.code()} - {e.details()}"}
    
    async def _tool_list_tools(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List tools from orchestrator registry."""
        # Query the orchestrator's metrics endpoint for tool info
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"http://{self.config.orchestrator_addr.replace(':50054', ':8888')}/tools",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except:
                pass
        
        # Fallback: return known tools
        return {
            "tools": [
                "get_commute_time",
                "get_calendar_events", 
                "web_search",
                "execute_code",
                "search_knowledge"
            ],
            "note": "This is a static list. Connect to orchestrator for live data."
        }
    
    async def _tool_service_health(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of all services with caching."""
        cache_key = "service_health"
        
        # Check cache first (30 second TTL)
        if cache_key in self._health_cache:
            logger.debug("Cache hit for service health")
            return self._health_cache[cache_key]
        
        services = {
            "orchestrator": self.config.orchestrator_addr,
            "chroma": self.config.chroma_addr,
            "sandbox": self.config.sandbox_addr,
        }
        
        health = {}
        for name, addr in services.items():
            try:
                channel = grpc.aio.insecure_channel(addr)
                # Simple connectivity check
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
                health[name] = "healthy"
                await channel.close()
            except Exception as e:
                health[name] = f"unhealthy: {e}"
        
        # Check dashboard via HTTP
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.config.dashboard_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    health["dashboard"] = "healthy" if resp.status == 200 else f"unhealthy: {resp.status}"
            except Exception as e:
                health["dashboard"] = f"unhealthy: {e}"
        
        # Cache the result
        self._health_cache[cache_key] = health
        return health

    async def _tool_daily_briefing(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a daily briefing by aggregating context."""
        include_weather = args.get("include_weather", True)
        include_commute = args.get("include_commute", True)
        
        briefing = {
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "generated_at": datetime.now().isoformat(),
            "sections": {}
        }
        
        # Fetch context from dashboard
        context = await self._tool_get_context({"user_id": "default", "time_range": "today"})
        
        if "error" not in context:
            briefing["sections"]["context"] = context
        
        # Get calendar via orchestrator
        calendar_result = await self._tool_query_agent({
            "query": "What meetings and events do I have scheduled today?",
            "category": "calendar"
        })
        if "error" not in calendar_result:
            briefing["sections"]["calendar"] = calendar_result.get("answer", "No calendar data")
        
        # Optional: weather
        if include_weather:
            weather_result = await self._tool_query_agent({
                "query": "What's the weather like today?",
                "category": "weather"
            })
            if "error" not in weather_result:
                briefing["sections"]["weather"] = weather_result.get("answer", "Weather unavailable")
        
        # Optional: commute to first meeting
        if include_commute and briefing.get("sections", {}).get("calendar"):
            commute_result = await self._tool_query_agent({
                "query": "What's my commute time to my first meeting today?",
                "category": "commute"
            })
            if "error" not in commute_result:
                briefing["sections"]["commute"] = commute_result.get("answer", "Commute info unavailable")
        
        return briefing

    async def _tool_plan_day(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a time-blocked schedule for the day."""
        work_start = args.get("work_start", "09:00")
        work_end = args.get("work_end", "18:00")
        include_breaks = args.get("include_breaks", True)
        priorities = args.get("priorities", [])
        
        # Fetch current context for calendar/tasks
        context = await self._tool_get_context({"user_id": "default", "time_range": "today"})
        
        # Use orchestrator to generate the plan
        plan_query = f"""Create a time-blocked schedule for today.
Work hours: {work_start} to {work_end}.
Include breaks: {include_breaks}.
Priority tasks: {', '.join(priorities) if priorities else 'None specified'}.

Based on my calendar and tasks, create an optimal schedule with:
1. Fixed meetings/events at their scheduled times
2. Time blocks for priority tasks
3. Buffer time between meetings
{'4. Break times every 90 minutes' if include_breaks else ''}

Format as a timeline."""
        
        plan_result = await self._tool_query_agent({
            "query": plan_query,
            "category": "calendar"
        })
        
        return {
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "work_hours": {"start": work_start, "end": work_end},
            "priorities": priorities,
            "plan": plan_result.get("answer", "Unable to generate plan"),
            "context_used": plan_result.get("context_used", [])
        }

    # =========================================================================
    # Server Lifecycle
    # =========================================================================
    
    async def start(self):
        """Start the MCP server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        logger.info(f"MCP Server started on http://{self.config.host}:{self.config.port}")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.bridge.close()
            await runner.cleanup()


def main():
    """Entry point."""
    config = MCPServerConfig(
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8100")),
        orchestrator_addr=os.getenv("ORCHESTRATOR_ADDR", "orchestrator:50054"),
        chroma_addr=os.getenv("CHROMA_ADDR", "chroma_service:50052"),
        sandbox_addr=os.getenv("SANDBOX_ADDR", "sandbox_service:50057"),
        dashboard_url=os.getenv("DASHBOARD_URL", "http://dashboard:8001"),
        openclaw_url=os.getenv("OPENCLAW_URL", "http://host.docker.internal:18789"),
    )
    
    server = MCPServer(config)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
