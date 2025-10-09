import grpc
import sys
sys.path.insert(0, '..')
from llm_service import llm_pb2, llm_pb2_grpc


def run():
    channel = grpc.insecure_channel('localhost:50051')
    stub = llm_pb2_grpc.LLMServiceStub(channel)
    req = llm_pb2.GenerateRequest(prompt='Write a short poem about AI and coffee.', max_tokens=50, temperature=0.7, response_format='text')
    print('LLM streaming response:')
    for resp in stub.Generate(req):
        print(resp.token, end='')
        if resp.is_final:
            break


if __name__ == '__main__':
    run()
