import grpc
from concurrent import futures
import subprocess
import shlex
import llm_pb2
import llm_pb2_grpc

# Path to your llama-cli binary and model file
LLAMA_CLI_PATH = "./llama/llama-cli"
MODEL_PATH = "/models/qwen2.5-0.5b-instruct-q5_k_m.gguf"

class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        prompt = request.prompt
        max_tokens = request.max_tokens or 512
        temperature = request.temperature or 0.8

        command = f"{LLAMA_CLI_PATH} --model {MODEL_PATH} --prompt {shlex.quote(prompt)} --n-predict {max_tokens} --temp {temperature}"
        process = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        for stdout_line in iter(process.stdout.readline, ""):
            yield llm_pb2.GenerateResponse(token=stdout_line.strip(), is_final=False)
        process.stdout.close()
        process.wait()
        yield llm_pb2.GenerateResponse(token="", is_final=True)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()