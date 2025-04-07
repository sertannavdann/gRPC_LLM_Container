import grpc
import logging
from typing import Any

class TestClient:
    __test__ = False 
    def __init__(self, service_config: dict):
        self.channel = grpc.insecure_channel(
            f"{service_config['host']}:{service_config['port']}"
        )
        self.stub = service_config['stub'](self.channel)
        self.logger = logging.getLogger(service_config['name'])

    def call(self, method: str, request: Any, timeout=10):
        try:
            return getattr(self.stub, method)(request, timeout=timeout)
        except grpc.RpcError as e:
            self.logger.error(f"{method} failed: {e.code().name}")
            raise