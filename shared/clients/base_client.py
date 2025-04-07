import grpc
import logging
from typing import Dict, Tuple
from tenacity import retry, wait_exponential, stop_after_attempt, before_log

logger = logging.getLogger(__name__)

class BaseClient:
    """
    Production-grade base client with proper retry decorator exposure
    """
    _channels: Dict[Tuple[str, int], grpc.Channel] = {}
    _RETRY_CONFIG = {
        'stop': stop_after_attempt(3),
        'wait': wait_exponential(multiplier=1, max=10),
        'before': before_log(logger, logging.DEBUG)
    }

    def __init__(self, service_name: str, port: int):
        self.service_name = service_name
        self.port = port
        self.channel = self._get_channel(service_name, port)
        self._configure_retries()

    @classmethod
    def _get_channel(cls, service: str, port: int) -> grpc.Channel:
        """Channel factory with connection pooling"""
        key = (service, port)
        if key not in cls._channels:
            cls._channels[key] = grpc.insecure_channel(
                f"{service}:{port}",
                options=[
                    ('grpc.keepalive_time_ms', 10000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.enable_retries', 1)
                ]
            )
            logger.info(f"Initialized channel to {service}:{port}")
        return cls._channels[key]

    @classmethod
    def retry_decorator(cls):
        """Explicit retry decorator for method-level control"""
        return retry(**cls._RETRY_CONFIG)

    def _configure_retries(self):
        """Auto-configure retries for public methods"""
        for name in dir(self):
            if name.startswith('_'):
                continue
            method = getattr(self, name)
            if callable(method) and not hasattr(method, '_no_retry'):
                setattr(self, name, self.retry_decorator()(method))

    @classmethod
    def shutdown(cls):
        """Graceful shutdown of all channels"""
        for channel in cls._channels.values():
            channel.close()
        cls._channels.clear()
        logger.info("All gRPC channels closed")