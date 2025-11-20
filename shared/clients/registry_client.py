import grpc
import logging
from shared.generated import registry_pb2
from shared.generated import registry_pb2_grpc

logger = logging.getLogger(__name__)

class RegistryClient:
    def __init__(self, host="registry_service", port=50055):
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = registry_pb2_grpc.AgentRegistryStub(self.channel)
        logger.info(f"RegistryClient connected to {host}:{port}")

    def register(self, agent_id, name, capabilities, endpoint):
        try:
            request = registry_pb2.AgentProfile(
                id=agent_id,
                name=name,
                capabilities=capabilities,
                endpoint=endpoint
            )
            response = self.stub.Register(request)
            return response.success
        except grpc.RpcError as e:
            logger.error(f"Failed to register: {e}")
            return False

    def discover(self, capability):
        try:
            request = registry_pb2.CapabilityQuery(capability=capability)
            response = self.stub.Discover(request)
            return response.agents
        except grpc.RpcError as e:
            logger.error(f"Failed to discover agents for {capability}: {e}")
            return []
