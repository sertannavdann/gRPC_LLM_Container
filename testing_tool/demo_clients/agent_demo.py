import grpc
import sys
sys.path.insert(0, '..')
from agent_service import agent_pb2, agent_pb2_grpc


def run():
    channel = grpc.insecure_channel('localhost:50054')
    stub = agent_pb2_grpc.AgentServiceStub(channel)
    req = agent_pb2.AgentRequest(user_query='Explain quantum computing in simple terms')
    resp = stub.QueryAgent(req)
    print('Agent final answer:')
    print(resp.final_answer)

if __name__ == '__main__':
    run()
