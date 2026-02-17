"""Base class for online/cloud-based LLM providers using OpenAI-compatible API."""

import aiohttp
import logging
from typing import List, AsyncIterator, Dict, Any, Optional
from .base_provider import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ModelInfo,
    ChatRequest,
    ChatResponse,
    ProviderConnectionError,
    ProviderAuthError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class OnlineProvider(BaseProvider):
    """
    Base class for online/cloud-based LLM providers.

    Handles OpenAI-compatible REST API interactions with:
    - HTTP client management
    - Error handling and rate limiting
    - Authentication via API keys
    - Streaming and non-streaming completions
    """

    def __init__(
        self,
        config: ProviderConfig,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize OnlineProvider.

        Args:
            config: ProviderConfig with provider settings
            base_url: Optional override for API base URL
            api_key: Optional override for API key
        """
        super().__init__(config)
        self.base_url = base_url or config.base_url
        self.api_key = api_key or config.api_key
        self.timeout = aiohttp.ClientTimeout(total=config.timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._available_models: List[ModelInfo] = []

        if not self.api_key:
            logger.warning(f"No API key provided for {self.name}")

        logger.info(
            f"{self.name.upper()}Provider initialized with base_url: {self.base_url}"
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate(self, request: ChatRequest) -> ChatResponse:
        """
        Generate a completion using online API.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            ChatResponse with model output

        Raises:
            ProviderAuthError: If authentication fails
            ProviderConnectionError: If API call fails
            ProviderRateLimitError: If rate limited
        """
        payload = self._build_payload(request)
        headers = self._build_headers()

        try:
            session = await self._get_session()
            url = f"{self.base_url}/chat/completions"

            async with session.post(
                url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 401:
                    raise ProviderAuthError("Authentication failed: Invalid API key")
                elif response.status == 429:
                    raise ProviderRateLimitError("Rate limited by provider")
                elif response.status >= 400:
                    error_text = await response.text()
                    raise ProviderConnectionError(f"API error {response.status}: {error_text}")

                data = await response.json()
                return self._parse_response(data, request.model)

        except aiohttp.ClientError as e:
            raise ProviderConnectionError(f"Connection failed: {str(e)}")
        except Exception as e:
            logger.error(f"Generate request failed: {str(e)}")
            raise ProviderConnectionError(f"Generate request failed: {str(e)}")

    async def generate_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Generate a streaming completion using online API.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            String tokens as they become available

        Raises:
            ProviderAuthError: If authentication fails
            ProviderConnectionError: If API call fails
            ProviderRateLimitError: If rate limited
        """
        payload = self._build_payload(request)
        payload["stream"] = True
        headers = self._build_headers()

        try:
            session = await self._get_session()
            url = f"{self.base_url}/chat/completions"

            async with session.post(
                url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 401:
                    raise ProviderAuthError("Authentication failed: Invalid API key")
                elif response.status == 429:
                    raise ProviderRateLimitError("Rate limited by provider")
                elif response.status >= 400:
                    error_text = await response.text()
                    raise ProviderConnectionError(f"API error {response.status}: {error_text}")

                async for line in response.content:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            import json

                            chunk = json.loads(data_str)
                            token = self._extract_token(chunk)
                            if token:
                                yield token
                        except Exception as e:
                            logger.debug(f"Error parsing stream chunk: {str(e)}")
                            continue

        except aiohttp.ClientError as e:
            raise ProviderConnectionError(f"Streaming connection failed: {str(e)}")
        except Exception as e:
            logger.error(f"Stream request failed: {str(e)}")
            raise ProviderConnectionError(f"Stream request failed: {str(e)}")

    async def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from provider.

        Returns:
            List of ModelInfo instances
        """
        if self._available_models:
            return self._available_models

        # Subclasses should override with actual model list
        return self._get_default_models()

    def _get_default_models(self) -> List[ModelInfo]:
        """
        Get default list of models if API doesn't provide one.

        Subclasses override for provider-specific models.

        Returns:
            List of ModelInfo instances
        """
        return []

    async def health_check(self) -> bool:
        """
        Check if provider API is accessible.

        Returns:
            True if provider is healthy, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/models"
            headers = self._build_headers()

            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(url, headers=headers, timeout=timeout) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Health check failed: {str(e)}")
            return False

    def _build_headers(self) -> Dict[str, str]:
        """
        Build HTTP headers for API request.

        Subclasses can override for provider-specific headers.

        Returns:
            Dictionary of headers
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(self, request: ChatRequest) -> Dict[str, Any]:
        """
        Build request payload for API.

        Subclasses can override for provider-specific formatting.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            Dictionary payload for API
        """
        messages = []
        for msg in request.messages:
            if hasattr(msg, "role"):
                messages.append({"role": msg.role, "content": msg.content})
            else:
                messages.append(msg)

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
        }

        if request.tools:
            payload["tools"] = request.tools

        if request.extra:
            payload.update(request.extra)

        return payload

    def _parse_response(self, response: Dict[str, Any], model: str) -> ChatResponse:
        """
        Parse API response into ChatResponse.

        Subclasses can override for provider-specific parsing.

        Args:
            response: Raw API response dictionary
            model: Model name from request

        Returns:
            ChatResponse instance
        """
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        stop_reason = choice.get("finish_reason", "stop")

        usage = response.get("usage", {})
        parsed_usage = None
        if usage:
            parsed_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }

        return ChatResponse(
            model=model,
            content=content,
            stop_reason=stop_reason,
            usage=parsed_usage,
            raw_response=response,
        )

    def _extract_token(self, chunk: Dict[str, Any]) -> Optional[str]:
        """
        Extract token from streaming chunk.

        Subclasses can override for provider-specific format.

        Args:
            chunk: Parsed chunk dictionary

        Returns:
            Token string or None
        """
        choice = chunk.get("choices", [{}])[0]
        delta = choice.get("delta", {})
        return delta.get("content", None)
