import grpc
import agent_pb2
import agent_pb2_grpc

def run():
    channel = grpc.insecure_channel('localhost:50054')
    stub = agent_pb2_grpc.AgentServiceStub(channel)
    request = agent_pb2.AgentRequest(user_query="What is the capital of France?")
    response = stub.QueryAgent(request)
    print("Final Answer:", response.final_answer)

if __name__ == "__main__":
    run()
