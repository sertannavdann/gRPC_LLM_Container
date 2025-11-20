import logging
import time
import uuid
import os
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection

from shared.generated import worker_pb2
from shared.generated import worker_pb2_grpc
from shared.clients.registry_client import RegistryClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("worker_service")

class WorkerService(worker_pb2_grpc.WorkerServiceServicer):
    def __init__(self, worker_id, capabilities):
        self.worker_id = worker_id
        self.capabilities = capabilities
        logger.info(f"Worker Service initialized (ID: {worker_id})")

    def ExecuteTask(self, request, context):
        logger.info(f"Received task {request.task_id}: {request.instruction}")
        
        # Simple execution logic for demo
        try:
            # Simulate work
            result = f"Executed: {request.instruction}. Context length: {len(request.context)}"
            
            # If it's a "coding" task (demo)
            if "coding" in self.capabilities and "code" in request.instruction.lower():
                result = "def hello():\n    print('Hello from Worker!')"
            
            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                status="success",
                result=result,
                error_message=""
            )
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                status="error",
                result="",
                error_message=str(e)
            )

def serve():
    # Configuration
    worker_id = os.getenv("WORKER_ID", str(uuid.uuid4()))
    worker_name = os.getenv("WORKER_NAME", "generic-worker")
    capabilities = os.getenv("WORKER_CAPABILITIES", "general").split(",")
    port = int(os.getenv("WORKER_PORT", "50056"))
    registry_host = os.getenv("REGISTRY_HOST", "registry_service")
    registry_port = int(os.getenv("REGISTRY_PORT", "50055"))
    host_ip = os.getenv("HOST_IP", "worker_service") # In docker-compose, service name

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    worker_pb2_grpc.add_WorkerServiceServicer_to_server(
        WorkerService(worker_id, capabilities), server
    )
    
    # Enable reflection
    SERVICE_NAMES = (
        worker_pb2.DESCRIPTOR.services_by_name['WorkerService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Worker Service started on port {port}")
    server.start()

    # Register with Registry
    try:
        registry_client = RegistryClient(host=registry_host, port=registry_port)
        # Wait for registry to be ready (simple retry)
        retries = 5
        while retries > 0:
            try:
                success = registry_client.register(
                    agent_id=worker_id,
                    name=worker_name,
                    capabilities=capabilities,
                    endpoint=f"{host_ip}:{port}"
                )
                if success:
                    logger.info("Successfully registered with Registry")
                    break
            except Exception as e:
                logger.warning(f"Registration failed, retrying... {e}")
            
            time.sleep(2)
            retries -= 1
    except Exception as e:
        logger.error(f"Failed to initialize registry client: {e}")

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
