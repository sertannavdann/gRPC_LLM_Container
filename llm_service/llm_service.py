#llm_service.py
import grpc
import logging
from concurrent import futures
from llama_cpp import Llama
import llm_pb2
import llm_pb2_grpc
from grpc_reflection.v1alpha import reflection
from functools import lru_cache
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("llm_service")

@lru_cache(maxsize=1)
def load_model():
    MODEL_PATH = "./models/qwen2.5-0.5b-instruct-q5_k_m.gguf"
    logger.info("Loading model from %s", MODEL_PATH)
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=2048,
        n_threads=4,
        n_batch=512,
        verbose=False
    )

class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        try:
            llm = load_model()
            gen_config = {
                "max_tokens": min(request.max_tokens, 1024),
                "temperature": max(0.1, min(request.temperature, 1.0)),
                "top_p": 0.95,
                "repeat_penalty": 1.1,
                "stream": True
            }
            
            token_produced = False
            for output in llm(request.prompt, **gen_config):
                if context.is_active():
                    token_produced = True
                    yield llm_pb2.GenerateResponse(
                        token=output["choices"][0]["text"],
                        is_final=False
                    )
                else:
                    logger.warning("Client disconnected, aborting generation")
                    break
            
            if not token_produced:
                logger.warning("No tokens produced during generation")
            
            yield llm_pb2.GenerateResponse(token="", is_final=True)
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            context.abort(grpc.StatusCode.INTERNAL, f"Generation error: {str(e)}")

class HealthServicer(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    
    reflection.enable_server_reflection([
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    server.add_insecure_port("[::]:50051")
    logger.info("LLM Service operational on port 50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()