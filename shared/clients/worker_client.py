import grpc
import logging
from shared.generated import worker_pb2
from shared.generated import worker_pb2_grpc

logger = logging.getLogger(__name__)

class WorkerClient:
    def __init__(self, endpoint):
        self.channel = grpc.insecure_channel(endpoint)
        self.stub = worker_pb2_grpc.WorkerServiceStub(self.channel)
        logger.info(f"WorkerClient connected to {endpoint}")

    def execute_task(self, task_id, instruction, context="", input_data=None):
        try:
            request = worker_pb2.TaskRequest(
                task_id=task_id,
                instruction=instruction,
                context=context,
                input_data=input_data or {}
            )
            response = self.stub.ExecuteTask(request)
            return response
        except grpc.RpcError as e:
            logger.error(f"Failed to execute task on worker: {e}")
            return None
