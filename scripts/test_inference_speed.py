"""Quick inference speed test for the running LLM service."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grpc
import time
from llm_service.llm_pb2 import GenerateRequest
from llm_service.llm_pb2_grpc import LLMServiceStub

ch = grpc.insecure_channel("localhost:50051")
stub = LLMServiceStub(ch)

prompts = [
    ("Cold", "Say OK", 16),
    ("Warm1", "What is 2+2? Answer in one word.", 16),
    ("Warm2", "Name 3 colors.", 32),
]

for label, prompt, max_tok in prompts:
    t0 = time.time()
    # Generate is server-streaming, collect all tokens
    tokens = []
    for chunk in stub.Generate(GenerateRequest(prompt=prompt, max_tokens=max_tok, temperature=0.1), timeout=60):
        tokens.append(chunk.token)
    elapsed = time.time() - t0
    text = "".join(tokens).strip()
    print(f"{label}: {text!r}  ({elapsed:.1f}s)")
