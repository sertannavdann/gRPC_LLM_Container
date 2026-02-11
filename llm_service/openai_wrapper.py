"""
OpenAI-Compatible HTTP API Wrapper for gRPC LLM Service

This server provides an OpenAI-compatible /v1/chat/completions endpoint
that proxies requests to the gRPC LLM service.

Usage:
    python openai_wrapper.py [--port 8080] [--grpc-host localhost] [--grpc-port 50051]

Endpoints:
    POST /v1/chat/completions - OpenAI-compatible chat completions
    GET  /v1/models           - List available models
    GET  /health              - Health check
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import AsyncGenerator, List, Optional

import grpc
from aiohttp import web

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from llm_service import llm_pb2, llm_pb2_grpc
except ImportError:
    import llm_pb2
    import llm_pb2_grpc

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("openai_wrapper")

# Configuration
GRPC_HOST = os.getenv("GRPC_LLM_HOST", "localhost")
GRPC_PORT = int(os.getenv("GRPC_LLM_PORT", "50051"))
HTTP_PORT = int(os.getenv("OPENAI_WRAPPER_PORT", "8080"))
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-local")


class GRPCClient:
    """Async gRPC client for LLM service."""
    
    def __init__(self, host: str, port: int):
        self.address = f"{host}:{port}"
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[llm_pb2_grpc.LLMServiceStub] = None
    
    async def connect(self):
        """Establish gRPC connection."""
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.address)
            self._stub = llm_pb2_grpc.LLMServiceStub(self._channel)
            logger.info(f"Connected to gRPC LLM service at {self.address}")
    
    async def close(self):
        """Close gRPC connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
    
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        stream: bool = False
    ) -> AsyncGenerator[str, None]:
        """Generate text from prompt."""
        await self.connect()
        
        request = llm_pb2.GenerateRequest(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format="text"
        )
        
        try:
            async for response in self._stub.Generate(request):
                yield response.text
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise


def format_chat_prompt(messages: List[dict]) -> str:
    """Convert OpenAI chat messages to a prompt string."""
    prompt_parts = []
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            prompt_parts.append(f"<|im_start|>system\n{content}<|im_end|>")
        elif role == "user":
            prompt_parts.append(f"<|im_start|>user\n{content}<|im_end|>")
        elif role == "assistant":
            prompt_parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
    
    # Add assistant prompt start
    prompt_parts.append("<|im_start|>assistant\n")
    
    return "\n".join(prompt_parts)


async def handle_chat_completions(request: web.Request) -> web.Response:
    """Handle POST /v1/chat/completions"""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response(
            {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
            status=400
        )
    
    messages = body.get("messages", [])
    if not messages:
        return web.json_response(
            {"error": {"message": "messages is required", "type": "invalid_request_error"}},
            status=400
        )
    
    # Extract parameters
    max_tokens = body.get("max_tokens", 1024)
    temperature = body.get("temperature", 0.7)
    stream = body.get("stream", False)
    model = body.get("model", MODEL_NAME)
    
    # Convert messages to prompt
    prompt = format_chat_prompt(messages)
    
    # Get gRPC client from app
    grpc_client: GRPCClient = request.app["grpc_client"]
    
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    
    if stream:
        # Streaming response
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(request)
        
        try:
            async for token in grpc_client.generate(prompt, max_tokens, temperature, stream=True):
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": token},
                        "finish_reason": None
                    }]
                }
                await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
            
            # Send final chunk
            final_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            await response.write(f"data: {json.dumps(final_chunk)}\n\n".encode())
            await response.write(b"data: [DONE]\n\n")
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_chunk = {"error": {"message": str(e)}}
            await response.write(f"data: {json.dumps(error_chunk)}\n\n".encode())
        
        return response
    
    else:
        # Non-streaming response
        try:
            full_response = ""
            async for token in grpc_client.generate(prompt, max_tokens, temperature):
                full_response += token
            
            return web.json_response({
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_response.strip()
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": len(full_response.split()),
                    "total_tokens": len(prompt.split()) + len(full_response.split())
                }
            })
            
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )


async def handle_models(request: web.Request) -> web.Response:
    """Handle GET /v1/models"""
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
                "permission": [],
                "root": MODEL_NAME,
                "parent": None
            }
        ]
    })


async def handle_health(request: web.Request) -> web.Response:
    """Handle GET /health"""
    grpc_client: GRPCClient = request.app["grpc_client"]
    try:
        await grpc_client.connect()
        return web.json_response({"status": "healthy", "grpc": "connected"})
    except Exception as e:
        return web.json_response({"status": "unhealthy", "error": str(e)}, status=503)


async def on_startup(app: web.Application):
    """Initialize gRPC client on startup."""
    app["grpc_client"] = GRPCClient(GRPC_HOST, GRPC_PORT)
    logger.info(f"OpenAI wrapper starting on port {HTTP_PORT}")
    logger.info(f"gRPC backend: {GRPC_HOST}:{GRPC_PORT}")


async def on_cleanup(app: web.Application):
    """Cleanup gRPC client on shutdown."""
    await app["grpc_client"].close()


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application()
    
    # Add routes
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)
    
    # Add lifecycle hooks
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenAI-compatible wrapper for gRPC LLM")
    parser.add_argument("--port", type=int, default=HTTP_PORT, help="HTTP server port")
    parser.add_argument("--grpc-host", default=GRPC_HOST, help="gRPC LLM host")
    parser.add_argument("--grpc-port", type=int, default=GRPC_PORT, help="gRPC LLM port")
    parser.add_argument("--model-name", default=MODEL_NAME, help="Model name to report")
    args = parser.parse_args()
    
    # Update globals
    GRPC_HOST = args.grpc_host
    GRPC_PORT = args.grpc_port
    HTTP_PORT = args.port
    MODEL_NAME = args.model_name
    
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=args.port)
