import grpc
import logging
from typing import Dict, Tuple, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, before_log

logger = logging.getLogger(__name__)

class BaseClient:
    """
    Base gRPC client with connection pooling and retry capabilities
    Handles channel lifecycle management for all services
    """
    _channels: Dict[Tuple[str, int], grpc.Channel] = {}
    _DEFAULT_RETRY_POLICY = {
        'retry': True,
        'max_attempts': 3,
        'max_wait': 10  # seconds
    }

    def __init__(self, service_name: str, port: int):
        self.service_name = service_name
        self.port = port
        self.channel = self._get_channel()
        self._configure_retries()

    @classmethod
    def _get_channel(cls, service: str, port: int) -> grpc.Channel:
        """Get or create shared channel with connection pooling"""
        key = (service, port)
        if key not in cls._channels:
            cls._channels[key] = grpc.insecure_channel(
                f"{service}:{port}",
                options=[
                    ('grpc.keepalive_time_ms', 10000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.enable_retries', 1),
                    ('grpc.service_config', 
                     '{"retryPolicy": { '
                     '"maxAttempts": 3, '
                     '"initialBackoff": "0.1s", '
                     '"maxBackoff": "1s", '
                     '"backoffMultiplier": 2, '
                     '"retryableStatusCodes": ["UNAVAILABLE"]}}')
                ]
            )
            logger.info(f"Created new channel to {service}:{port}")
        return cls._channels[key]

    def _configure_retries(self):
        """Apply retry decorator to all public methods"""
        for name in dir(self):
            if name.startswith('_'):
                continue
            method = getattr(self, name)
            if callable(method) and self._should_retry(method):
                setattr(self, name, self._retry_decorator()(method))

    def _should_retry(self, method) -> bool:
        """Determine if method should have retry decorator"""
        return getattr(method, '_retryable', False)

    @classmethod
    def _retry_decorator(cls):
        """Shared retry configuration"""
        return retry(
            wait=wait_exponential(
                multiplier=1, 
                max=cls._DEFAULT_RETRY_POLICY['max_wait']
            ),
            stop=stop_after_attempt(
                cls._DEFAULT_RETRY_POLICY['max_attempts']
            ),
            before=before_log(logger, logging.DEBUG)
        )

    @classmethod
    def shutdown(cls):
        """Cleanup all channels during graceful shutdown"""
        for channel in cls._channels.values():
            channel.close()
        cls._channels.clear()
        logger.info("All gRPC channels closed")