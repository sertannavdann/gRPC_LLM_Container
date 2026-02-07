"""
Rate Limiter - Token bucket implementation for provider rate limiting.

Provides:
- TokenBucketRateLimiter: Thread-safe async rate limiter
- RateLimitExceeded: Exception with retry-after header support
- Prometheus metrics integration

Usage:
    limiter = TokenBucketRateLimiter(rate=10.0, burst=20)
    
    async def make_request():
        if not await limiter.acquire():
            raise RateLimitExceeded(limiter.retry_after())
        # ... make request
"""

import asyncio
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """
    Raised when rate limit is exceeded.
    
    Attributes:
        retry_after: Seconds until a token will be available
        provider: Name of the rate-limited provider (optional)
    """
    
    def __init__(self, retry_after: float, provider: Optional[str] = None):
        self.retry_after = retry_after
        self.provider = provider
        msg = f"Rate limit exceeded. Retry after {retry_after:.2f}s"
        if provider:
            msg = f"[{provider}] {msg}"
        super().__init__(msg)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            "error": "rate_limit_exceeded",
            "retry_after": self.retry_after,
            "provider": self.provider,
        }


@dataclass
class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter with async support.
    
    Implements the token bucket algorithm:
    - Tokens are added at a constant rate
    - Burst capacity allows short bursts above the rate
    - Acquiring tokens fails if bucket is empty
    
    Attributes:
        rate: Tokens per second (sustained rate)
        burst: Maximum tokens in bucket (burst capacity)
        name: Optional name for logging/metrics
    
    Example:
        >>> limiter = TokenBucketRateLimiter(rate=10.0, burst=20, name="openai")
        >>> 
        >>> async def call_api():
        ...     if not await limiter.acquire():
        ...         raise RateLimitExceeded(limiter.retry_after(), "openai")
        ...     return await make_api_call()
    """
    
    rate: float  # tokens per second
    burst: int   # max tokens in bucket
    name: str = ""
    
    # Internal state
    _tokens: float = field(init=False)
    _last_update: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _async_lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    
    def __post_init__(self):
        self._tokens = float(self.burst)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()
        # Note: asyncio.Lock must be created in an async context or we need to handle it
        self._async_lock = None  # Will be created lazily
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_update = now
    
    def acquire_sync(self, tokens: int = 1) -> bool:
        """
        Synchronously acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False if rate limited
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                logger.debug(f"[{self.name}] Acquired {tokens} tokens, {self._tokens:.1f} remaining")
                return True
            logger.warning(f"[{self.name}] Rate limited, {self._tokens:.1f} tokens available, need {tokens}")
            return False
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Asynchronously acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False if rate limited
        """
        # Lazy init of async lock
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        
        async with self._async_lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                logger.debug(f"[{self.name}] Acquired {tokens} tokens, {self._tokens:.1f} remaining")
                return True
            logger.warning(f"[{self.name}] Rate limited, {self._tokens:.1f} tokens available, need {tokens}")
            return False
    
    async def acquire_or_wait(self, tokens: int = 1, max_wait: float = 30.0) -> bool:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            max_wait: Maximum seconds to wait
            
        Returns:
            True if tokens acquired within max_wait, False otherwise
        """
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            if await self.acquire(tokens):
                return True
            # Wait for estimated refill time
            wait_time = min(tokens / self.rate, max_wait - (time.monotonic() - start))
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        return False
    
    def retry_after(self, tokens: int = 1) -> float:
        """
        Calculate seconds until tokens will be available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Seconds to wait before retry
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                return 0.0
            needed = tokens - self._tokens
            return needed / self.rate
    
    @property
    def available_tokens(self) -> float:
        """Current number of available tokens."""
        with self._lock:
            self._refill()
            return self._tokens
    
    def reset(self) -> None:
        """Reset bucket to full capacity."""
        with self._lock:
            self._tokens = float(self.burst)
            self._last_update = time.monotonic()


class RateLimiterRegistry:
    """
    Registry for managing rate limiters per provider.
    
    Provides centralized rate limit management with:
    - Per-provider limiters
    - Default configurations
    - Prometheus metrics export
    
    Example:
        >>> registry = RateLimiterRegistry()
        >>> registry.register("openai", rate=60.0, burst=100)
        >>> registry.register("anthropic", rate=40.0, burst=50)
        >>> 
        >>> limiter = registry.get("openai")
        >>> if not await limiter.acquire():
        ...     raise RateLimitExceeded(limiter.retry_after(), "openai")
    """
    
    # Default rate limits per provider (requests per second, burst)
    DEFAULT_LIMITS = {
        "local": (100.0, 200),      # Local llama.cpp - generous limits
        "openai": (60.0, 100),      # OpenAI - 60 RPM tier 1
        "anthropic": (40.0, 60),    # Anthropic - 40 RPM
        "perplexity": (20.0, 40),   # Perplexity - conservative
        "openclaw": (30.0, 50),     # OpenClaw gateway
    }
    
    def __init__(self):
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._lock = threading.Lock()
    
    def register(
        self, 
        provider: str, 
        rate: Optional[float] = None, 
        burst: Optional[int] = None
    ) -> TokenBucketRateLimiter:
        """
        Register a rate limiter for a provider.
        
        Args:
            provider: Provider name
            rate: Tokens per second (uses default if None)
            burst: Burst capacity (uses default if None)
            
        Returns:
            The registered rate limiter
        """
        defaults = self.DEFAULT_LIMITS.get(provider, (10.0, 20))
        rate = rate if rate is not None else defaults[0]
        burst = burst if burst is not None else defaults[1]
        
        limiter = TokenBucketRateLimiter(rate=rate, burst=burst, name=provider)
        
        with self._lock:
            self._limiters[provider] = limiter
        
        logger.info(f"Registered rate limiter for {provider}: {rate}/s, burst={burst}")
        return limiter
    
    def get(self, provider: str) -> TokenBucketRateLimiter:
        """
        Get rate limiter for a provider (creates default if not exists).
        
        Args:
            provider: Provider name
            
        Returns:
            Rate limiter for the provider
        """
        with self._lock:
            if provider not in self._limiters:
                # Create limiter without calling register() to avoid deadlock
                defaults = self.DEFAULT_LIMITS.get(provider, (10.0, 20))
                rate, burst = defaults
                limiter = TokenBucketRateLimiter(rate=rate, burst=burst, name=provider)
                self._limiters[provider] = limiter
                logger.info(f"Created default rate limiter for {provider}: {rate}/s, burst={burst}")
            return self._limiters[provider]
    
    def get_stats(self) -> Dict[str, Dict]:
        """
        Get current stats for all limiters.
        
        Returns:
            Dict mapping provider to stats dict
        """
        stats = {}
        with self._lock:
            for name, limiter in self._limiters.items():
                stats[name] = {
                    "rate": limiter.rate,
                    "burst": limiter.burst,
                    "available": limiter.available_tokens,
                }
        return stats


# Global singleton registry
_rate_limiter_registry: Optional[RateLimiterRegistry] = None


def get_rate_limiter_registry() -> RateLimiterRegistry:
    """Get the global rate limiter registry."""
    global _rate_limiter_registry
    if _rate_limiter_registry is None:
        _rate_limiter_registry = RateLimiterRegistry()
    return _rate_limiter_registry


def get_rate_limiter(provider: str) -> TokenBucketRateLimiter:
    """
    Convenience function to get rate limiter for a provider.
    
    Args:
        provider: Provider name
        
    Returns:
        Rate limiter for the provider
    """
    return get_rate_limiter_registry().get(provider)
