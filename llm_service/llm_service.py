import grpc
import logging
from concurrent import futures
from llama_cpp import Llama
import llm_pb2
import llm_pb2_grpc
from grpc_reflection.v1alpha import reflection

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("llm_service")

# Model file path (ensure the file is available in /app/models/ inside your Linux container)
MODEL_PATH = "./models/qwen2.5-0.5b-instruct-q5_k_m.gguf"

logger.info("Loading model from %s", MODEL_PATH)
llm_model = Llama(model_path=MODEL_PATH, n_ctx=2048)
logger.info("Model loaded successfully.")

class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        prompt = request.prompt
        max_tokens = request.max_tokens or 512
        temperature = request.temperature or 0.8

        logger.info("Received prompt: %s", prompt)
        logger.info("Generation parameters: max_tokens=%d, temperature=%.2f", max_tokens, temperature)

        # Generation parameters (streaming enabled)
        gen_kwargs = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        
        try:
            # Iterate over streaming output from the model.
            for output in llm_model(prompt, **gen_kwargs):
                # Log the full output dictionary for debugging.
                logger.debug("Output dict: %s", output)
                # Extract the token from the first choice.
                token_text = output.get("choices", [{}])[0].get("text", "")
                logger.debug("Generated token: %r", token_text)
                yield llm_pb2.GenerateResponse(token=token_text, is_final=False)
        except Exception as e:
            logger.error("Error during generation: %s", str(e))
            context.abort(grpc.StatusCode.INTERNAL, str(e))
        
        # Final response marker.
        yield llm_pb2.GenerateResponse(token="", is_final=True)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)

    # Enable reflection for debugging with grpcurl.
    service_names = (
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port("[::]:50051")
    logger.info("LLM Service starting on port 50051...")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
