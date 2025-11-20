import logging
import time
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection

from shared.generated import registry_pb2
from shared.generated import registry_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("registry_service")

class RegistryService(registry_pb2_grpc.AgentRegistryServicer):
    def __init__(self):
        # In-memory store: {agent_id: AgentProfile}
        self.agents = {}
        logger.info("Registry Service initialized")

    def Register(self, request, context):
        logger.info(f"Registering agent: {request.name} (ID: {request.id}) with capabilities: {request.capabilities}")
        self.agents[request.id] = request
        return registry_pb2.Ack(success=True, message="Registered successfully")

    def Discover(self, request, context):
        capability = request.capability
        logger.info(f"Discovery request for capability: {capability}")
        
        matching_agents = []
        for agent in self.agents.values():
            if capability in agent.capabilities:
                matching_agents.append(agent)
        
        logger.info(f"Found {len(matching_agents)} agents for {capability}")
        return registry_pb2.AgentList(agents=matching_agents)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    registry_pb2_grpc.add_AgentRegistryServicer_to_server(RegistryService(), server)
    
    # Enable reflection
    SERVICE_NAMES = (
        registry_pb2.DESCRIPTOR.services_by_name['AgentRegistry'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    port = 50055
    server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Registry Service started on port {port}")
    server.start()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
