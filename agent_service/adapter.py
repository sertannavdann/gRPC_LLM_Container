"""
Integration adapter connecting gRPC interface to core framework.

Bridges legacy agent_pb2 messages with new core.graph.AgentWorkflow,
maintaining backward compatibility during migration period.

Example:
    >>> adapter = AgentServiceAdapter(checkpoint_db_path="./data/checkpoints.db")
    >>> adapter.set_llm_engine(llm_engine)
    >>> response = adapter.process_query(
    ...     query="What is 2+2?",
    ...     thread_id="user-123-session-1"
    ... )
"""

import logging
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from core import AgentWorkflow, WorkflowConfig
from core.state import create_initial_state
from core.checkpointing import CheckpointManager
from tools.registry import LocalToolRegistry
from shared.clients.cpp_llm_client import CppLLMClient
from tools.builtin.web_search import web_search
from tools.builtin.math_solver import math_solver
from tools.builtin.web_loader import load_web_page
from router import Router, RouterConfig
from prompts import AGENT_SYSTEM_PROMPT_TEMPLATE, AGENT_SIMPLE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AgentServiceAdapter:
    """
    Adapter translating gRPC requests to core framework operations.
    
    Architecture:
        gRPC Request → Adapter → AgentWorkflow → Core Framework → Adapter → gRPC Response
    
    Responsibilities:
        1. Convert protobuf messages to LangChain messages
        2. Initialize AgentWorkflow with tool registry
        3. Manage conversation checkpointing via thread_id
        4. Format responses back to protobuf
        5. Handle errors and logging
    
    Attributes:
        registry: LocalToolRegistry with built-in tools
        checkpoint_manager: CheckpointManager for conversation persistence
        checkpointer: SqliteSaver instance for LangGraph
        config: WorkflowConfig with LLM and iteration settings
        workflow: AgentWorkflow instance (set after LLM engine initialized)
        compiled_workflow: Compiled LangGraph app ready for invocation
    
    Example:
        >>> adapter = AgentServiceAdapter()
        >>> adapter.set_llm_engine(llm_engine)
        >>> response = adapter.process_query("Hello!", thread_id="conv-123")
        >>> print(response["content"])
    """
    
    def __init__(
        self,
        config: Optional[WorkflowConfig] = None,
        checkpoint_db_path: str = "./data/agent_checkpoints.db",
        system_prompt: Optional[str] = None,
        router_config: Optional[RouterConfig] = None,
        enable_router: bool = True,
    ):
        """
        Initialize adapter with tool registry and checkpoint manager.
        
        Args:
            config: Workflow configuration (uses defaults if None)
            checkpoint_db_path: Path to SQLite checkpoint database
            system_prompt: Optional system prompt for all conversations
            router_config: Optional router configuration
            enable_router: Whether to enable the embedded router (default: True)
        """
        # Initialize tool registry
        self.registry = LocalToolRegistry()
        self._register_builtin_tools()
        
        # Initialize checkpoint manager
        self.checkpoint_db_path = Path(checkpoint_db_path)
        self.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.checkpoint_manager = CheckpointManager(db_path=str(self.checkpoint_db_path))
        self.checkpointer = self.checkpoint_manager.create_checkpointer()
        
        # Initialize router
        self.enable_router = enable_router
        if self.enable_router:
            try:
                self.router = Router(config=router_config)
                logger.info("Router enabled")
            except Exception as e:
                logger.warning(f"Router initialization failed: {e}. Continuing without router.")
                self.enable_router = False
                self.router = None
        else:
            self.router = None
            logger.info("Router disabled")
        
        # Initialize workflow configuration
        self.config = config or WorkflowConfig(
            max_iterations=5,
            temperature=0.7,
            model_name="qwen2.5-0.5b-instruct",
            context_window=3,
            enable_streaming=False,
            timeout_seconds=30,
        )
        
        # System prompt (will be dynamically generated with router recommendation)
        self.base_system_prompt = system_prompt
        
        # Workflow (initialized after LLM engine is set)
        self.workflow: Optional[AgentWorkflow] = None
        self.compiled_workflow = None
        
        # Metrics tracking
        self.total_queries = 0
        self.successful_queries = 0
        self.failed_queries = 0
        self.router_calls = 0
        self.router_failures = 0
        
        logger.info(
            f"AgentServiceAdapter initialized: "
            f"checkpoint_db={checkpoint_db_path}, "
            f"tools={len(self.registry.tools)}, "
            f"max_iterations={self.config.max_iterations}, "
            f"router={'enabled' if self.enable_router else 'disabled'}"
        )
    
    def _register_builtin_tools(self):
        """Register all built-in tools with the registry."""
        try:
            self.registry.register(web_search)
            logger.info("Registered tool: web_search")
        except Exception as e:
            logger.warning(f"Failed to register web_search: {e}")
        
        try:
            self.registry.register(math_solver)
            logger.info("Registered tool: math_solver")
        except Exception as e:
            logger.warning(f"Failed to register math_solver: {e}")
        
        try:
            self.registry.register(load_web_page)
            logger.info("Registered tool: load_web_page")
        except Exception as e:
            logger.warning(f"Failed to register load_web_page: {e}")

        # Bridge tool for native C++ LLM service
        try:
            cpp_client = CppLLMClient()

            def cpp_llm_inference(query: str) -> dict:
                """Low-latency inference via native C++ microservice.

                Args:
                    query (str): Prompt to send to C++ LLM service

                Returns:
                    Dict with keys 'status', 'output', 'intent_payload'
                """
                result = cpp_client.run_inference(query)
                # Standardize result shape
                return {
                    "status": "success",
                    "output": result.get("output", ""),
                    "intent_payload": result.get("intent_payload", ""),
                }

            # Register with explicit name/description
            self.registry.register(name="cpp_llm_inference", description="Low-latency deterministic inference via C++ service")(cpp_llm_inference)
            logger.info("Registered tool: cpp_llm_inference")
        except Exception as e:
            logger.warning(f"Failed to register cpp_llm_inference: {e}")
        
        logger.info(f"Total tools registered: {len(self.registry.tools)}")
    
    def _build_system_prompt(self, router_recommendation: Optional[dict] = None) -> str:
        """
        Build system prompt with optional router recommendation.
        
        Args:
            router_recommendation: Optional router recommendation to inject
        
        Returns:
            str: System prompt for the agent
        """
        if self.base_system_prompt:
            # Use custom system prompt if provided
            return self.base_system_prompt
        
        # Use template-based prompt
        if router_recommendation:
            # Format router recommendation for display
            rec_text = json.dumps(router_recommendation, indent=2)
            return AGENT_SYSTEM_PROMPT_TEMPLATE.format(
                router_recommendation=rec_text
            )
        else:
            # No router recommendation, use simple prompt
            return AGENT_SIMPLE_SYSTEM_PROMPT
    
    def set_llm_engine(self, llm_engine):
        """
        Set LLM engine and initialize workflow.
        
        Must be called before processing queries. The LLM engine should
        implement the expected interface (generate method).
        
        Args:
            llm_engine: LLM engine instance (e.g., LLMClientWrapper)
        
        Raises:
            ValueError: If llm_engine is None
        """
        if llm_engine is None:
            raise ValueError("LLM engine cannot be None")
        
        self.workflow = AgentWorkflow(
            tool_registry=self.registry,
            llm_engine=llm_engine,
            config=self.config,
        )
        
        self.compiled_workflow = self.workflow.compile(self.checkpointer)
        
        logger.info(
            f"AgentWorkflow compiled: "
            f"model={self.config.model_name}, "
            f"checkpointing=enabled"
        )
    
    def process_query(
        self,
        query: str,
        thread_id: Optional[str] = None,
        context: Optional[List[dict]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process user query through agent workflow.
        
        This is the main entry point for query processing. It:
        1. Creates initial state with user message
        2. Invokes compiled workflow with checkpointing
        3. Extracts and formats response
        4. Handles errors gracefully
        
        Args:
            query: User's natural language query
            thread_id: Conversation thread ID for checkpointing (optional)
            context: Additional context documents (optional)
            user_id: User identifier for multi-tenant systems (optional)
        
        Returns:
            dict: Response with following keys:
                - status: "success", "partial", or "error"
                - content: Response text from LLM
                - tool_results: List of tool execution results
                - iteration_count: Number of workflow iterations
                - metadata: Additional metadata (thread_id, message_count, etc.)
                - error: Error message (if status != "success")
        
        Raises:
            RuntimeError: If LLM engine not set (call set_llm_engine first)
        
        Example:
            >>> response = adapter.process_query(
            ...     query="What is the weather in Paris?",
            ...     thread_id="user-456-session-2"
            ... )
            >>> print(response["content"])
            "I'll search for the weather in Paris..."
        """
        if not self.workflow or not self.compiled_workflow:
            raise RuntimeError(
                "LLM engine not initialized. Call set_llm_engine() first."
            )
        
        # Track metrics
        self.total_queries += 1
        start_time = datetime.now()
        
        # Create conversation ID (use thread_id or generate ephemeral)
        conversation_id = thread_id or f"ephemeral-{datetime.now().timestamp()}"
        
        logger.info(
            f"Processing query (total={self.total_queries}): "
            f"'{query[:50]}{'...' if len(query) > 50 else ''}' "
            f"(thread={conversation_id})"
        )
        
        try:
            # Step 1: Get router recommendation (if enabled)
            router_recommendation = None
            if self.enable_router and self.router:
                try:
                    self.router_calls += 1
                    router_recommendation = self.router.route(query)
                    logger.info(
                        f"Router recommendation: "
                        f"primary={router_recommendation.get('primary_service')}, "
                        f"confidence={router_recommendation.get('confidence', 0):.2f}, "
                        f"requires_tools={router_recommendation.get('requires_tools')}"
                    )
                except Exception as e:
                    self.router_failures += 1
                    logger.warning(f"Router failed, continuing without recommendation: {e}")
                    router_recommendation = None
            
            # Step 2: Create initial state with router recommendation
            initial_state = create_initial_state(
                conversation_id=conversation_id,
                user_id=user_id,
                metadata={
                    "context": context or [],
                    "query_timestamp": start_time.isoformat(),
                },
            )
            initial_state["router_recommendation"] = router_recommendation
            
            # Step 3: Build system prompt with router recommendation
            messages = []
            system_prompt = self._build_system_prompt(router_recommendation)
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            
            # Add user message
            messages.append(HumanMessage(content=query))
            initial_state["messages"] = messages
            
            # Configure checkpointing
            config = (
                {"configurable": {"thread_id": thread_id}}
                if thread_id
                else {}
            )
            
            # Invoke workflow
            result = self.compiled_workflow.invoke(initial_state, config=config)
            
            # Extract response
            messages = result.get("messages", [])
            last_message = messages[-1] if messages else None
            
            if not last_message:
                self.failed_queries += 1
                return {
                    "status": "error",
                    "error": "No response generated by workflow",
                    "content": "",
                    "tool_results": [],
                    "iteration_count": 0,
                    "metadata": {"thread_id": conversation_id},
                }
            
            # Extract content from last message
            content = ""
            if hasattr(last_message, "content"):
                content = last_message.content
            else:
                content = str(last_message)
            
            # Build response
            response = {
                "status": "success",
                "content": content,
                "tool_results": result.get("tool_results", []),
                "iteration_count": result.get("retry_count", 0),
                "router_recommendation": router_recommendation,  # Include router rec
                "metadata": {
                    "thread_id": conversation_id,
                    "message_count": len(messages),
                    "processing_time_ms": (
                        datetime.now() - start_time
                    ).total_seconds() * 1000,
                    "router_latency_ms": (
                        router_recommendation.get("latency_ms", 0)
                        if router_recommendation else 0
                    ),
                },
            }
            
            # Check for workflow errors
            if result.get("error"):
                response["status"] = "partial"
                response["error"] = result["error"]
                self.failed_queries += 1
            else:
                self.successful_queries += 1
            
            logger.info(
                f"Query processed: "
                f"status={response['status']}, "
                f"tools_used={len(response['tool_results'])}, "
                f"iterations={response['iteration_count']}, "
                f"time={response['metadata']['processing_time_ms']:.0f}ms"
            )
            
            return response
        
        except Exception as e:
            self.failed_queries += 1
            logger.error(f"Error processing query: {e}", exc_info=True)
            
            return {
                "status": "error",
                "error": str(e),
                "content": "",
                "tool_results": [],
                "iteration_count": 0,
                "metadata": {
                    "thread_id": conversation_id,
                    "processing_time_ms": (
                        datetime.now() - start_time
                    ).total_seconds() * 1000,
                },
            }
    
    def list_conversations(self, limit: int = 100) -> List[dict]:
        """
        List recent conversation threads.
        
        Args:
            limit: Maximum number of threads to return
        
        Returns:
            list[dict]: Thread metadata with IDs and timestamps
        
        Example:
            >>> threads = adapter.list_conversations(limit=10)
            >>> for thread in threads:
            ...     print(f"{thread['thread_id']}: {thread['last_updated']}")
        """
        try:
            return self.checkpoint_manager.list_threads(limit=limit)
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return []
    
    def delete_conversation(self, thread_id: str):
        """
        Delete conversation thread and all checkpoints.
        
        Args:
            thread_id: Conversation identifier to delete
        
        Example:
            >>> adapter.delete_conversation("user-123-session-1")
        """
        try:
            self.checkpoint_manager.delete_thread(thread_id)
            logger.info(f"Deleted conversation thread: {thread_id}")
        except Exception as e:
            logger.error(f"Error deleting conversation {thread_id}: {e}")
            raise
    
    def get_tool_registry(self) -> LocalToolRegistry:
        """
        Get tool registry for inspection or modification.
        
        Returns:
            LocalToolRegistry: The adapter's tool registry
        
        Example:
            >>> registry = adapter.get_tool_registry()
            >>> print(registry.get_available_tools())
        """
        return self.registry
    
    def get_metrics(self) -> dict:
        """
        Get adapter operational metrics.
        
        Returns:
            dict: Metrics including:
                - total_queries: Total queries processed
                - successful_queries: Queries completed successfully
                - failed_queries: Queries that encountered errors
                - success_rate: Percentage of successful queries
                - router_calls: Number of router invocations
                - router_failures: Number of router failures
                - router_success_rate: Router success percentage
                - tools_registered: Number of registered tools
                - tools_available: Number of tools with circuit breaker closed
                - checkpoint_db: Path to checkpoint database
        
        Example:
            >>> metrics = adapter.get_metrics()
            >>> print(f"Success rate: {metrics['success_rate']:.1f}%")
        """
        success_rate = (
            (self.successful_queries / self.total_queries * 100)
            if self.total_queries > 0
            else 0.0
        )
        
        router_success_rate = (
            ((self.router_calls - self.router_failures) / self.router_calls * 100)
            if self.router_calls > 0
            else 0.0
        )
        
        tools_available = len([
            name
            for name, tool in self.registry.tools.items()
            if self.registry.circuit_breakers[name].is_available()
        ])
        
        return {
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "failed_queries": self.failed_queries,
            "success_rate": success_rate,
            "router_enabled": self.enable_router,
            "router_calls": self.router_calls,
            "router_failures": self.router_failures,
            "router_success_rate": router_success_rate,
            "tools_registered": len(self.registry.tools),
            "tools_available": tools_available,
            "checkpoint_db": str(self.checkpoint_db_path),
        }
    
    def reset_circuit_breaker(self, tool_name: str):
        """
        Reset circuit breaker for a specific tool.
        
        Args:
            tool_name: Name of tool to reset
        
        Example:
            >>> adapter.reset_circuit_breaker("web_search")
        """
        try:
            self.registry.reset_circuit_breaker(tool_name)
            logger.info(f"Reset circuit breaker for tool: {tool_name}")
        except KeyError:
            logger.warning(f"Tool not found: {tool_name}")
            raise
    
    def health_check(self) -> dict:
        """
        Perform health check on adapter components.
        
        Returns:
            dict: Health status with:
                - status: "healthy" or "unhealthy"
                - components: Dict of component statuses
                - timestamp: Check timestamp
        
        Example:
            >>> health = adapter.health_check()
            >>> assert health["status"] == "healthy"
        """
        components = {}
        
        # Check workflow initialization
        components["workflow"] = {
            "status": "healthy" if self.workflow else "unhealthy",
            "message": "Workflow initialized" if self.workflow else "Workflow not initialized",
        }
        
        # Check checkpoint database
        try:
            db_exists = self.checkpoint_db_path.exists()
            components["checkpoint_db"] = {
                "status": "healthy" if db_exists else "warning",
                "message": f"Database at {self.checkpoint_db_path}",
            }
        except Exception as e:
            components["checkpoint_db"] = {
                "status": "unhealthy",
                "message": f"Error checking database: {e}",
            }
        
        # Check tool registry
        components["tool_registry"] = {
            "status": "healthy" if len(self.registry.tools) > 0 else "warning",
            "message": f"{len(self.registry.tools)} tools registered",
        }
        
        # Overall status
        overall_status = (
            "healthy"
            if all(c["status"] == "healthy" for c in components.values())
            else "unhealthy"
        )
        
        return {
            "status": overall_status,
            "components": components,
            "timestamp": datetime.now().isoformat(),
            "metrics": self.get_metrics(),
        }
