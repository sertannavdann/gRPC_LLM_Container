"""GitHub Models provider using GitHub AI inference endpoint."""

import asyncio
import logging
from typing import List, Dict, Any, Optional
import aiohttp

from .base_provider import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ModelInfo,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ProviderConnectionError,
    ProviderAuthError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class GitHubModelsProvider(BaseProvider):
    """
    Provider for GitHub Models inference API.

    Uses GitHub AI endpoint at https://models.github.ai/inference/chat/completions
    Supports org-attributed billing path for enterprise accounts.

    Key features:
    - Bearer token authentication
    - GitHub API versioning headers
    - Structured output via response_format json_schema
    - Retry with exponential backoff for transient errors (429, 5xx, timeout)
    - No retry on auth errors (401/403) or client errors (400)
    """

    DEFAULT_BASE_URL = "https://models.github.ai/inference"
    API_VERSION = "2022-11-28"
    MAX_RETRY_ATTEMPTS = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds

    # Default GitHub Models
    GITHUB_MODELS = [
        ModelInfo(
            name="gpt-4o",
            description="GPT-4o via GitHub Models",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="gpt-4o-mini",
            description="GPT-4o Mini via GitHub Models",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="o1-preview",
            description="OpenAI o1 Preview via GitHub Models",
            supports_streaming=False,
            supports_function_calling=False,
            context_window=128000,
            max_tokens=32768,
        ),
        ModelInfo(
            name="o1-mini",
            description="OpenAI o1 Mini via GitHub Models",
            supports_streaming=False,
            supports_function_calling=False,
            context_window=128000,
            max_tokens=65536,
        ),
    ]

    def __init__(
        self,
        config: ProviderConfig,
        org_id: Optional[str] = None
    ):
        """
        Initialize GitHub Models provider.

        Args:
            config: ProviderConfig with API settings
            org_id: Optional GitHub org ID for enterprise billing attribution
        """
        super().__init__(config)
        self.api_key = config.api_key
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.org_id = org_id
        self.timeout = aiohttp.ClientTimeout(total=config.timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self.name = "github_models"

        if not self.api_key:
            logger.warning("No API key provided for GitHub Models")

        logger.info(
            f"GitHubModelsProvider initialized with base_url: {self.base_url}, "
            f"org_attribution: {bool(org_id)}"
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

    def _build_headers(self) -> Dict[str, str]:
        """
        Build headers for GitHub Models API.

        Required headers:
        - Authorization: Bearer token
        - X-GitHub-Api-Version: API version
        - Accept: application/json
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-GitHub-Api-Version": self.API_VERSION,
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    def _build_endpoint(self) -> str:
        """
        Build endpoint URL with optional org attribution.

        Returns:
            URL for chat completions endpoint
        """
        if self.org_id:
            # Enterprise org-attributed path
            return f"{self.base_url}/orgs/{self.org_id}/chat/completions"
        else:
            # Standard unattributed path
            return f"{self.base_url}/chat/completions"

    def _build_payload(
        self,
        request: ChatRequest,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build request payload for GitHub Models API.

        Args:
            request: ChatRequest with messages and parameters
            response_format: Optional structured output schema

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

        # Add response_format if provided (for structured outputs)
        if response_format:
            payload["response_format"] = response_format

        # Add tools if provided
        if request.tools:
            payload["tools"] = request.tools

        # Add seed for reproducibility if in extra
        if "seed" in request.extra:
            payload["seed"] = request.extra["seed"]

        return payload

    def _parse_response(self, response: Dict[str, Any], model: str) -> ChatResponse:
        """
        Parse API response into ChatResponse.

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

        # Check for tool calls
        tool_calls = message.get("tool_calls")

        return ChatResponse(
            model=model,
            content=content,
            stop_reason=stop_reason,
            usage=parsed_usage,
            tool_calls=tool_calls,
            raw_response=response,
        )

    async def _retry_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        attempt: int = 1
    ) -> Dict[str, Any]:
        """
        Execute request with retry logic for transient failures.

        Retries on:
        - 429 (rate limit)
        - 5xx (server errors)
        - Timeout errors

        Does NOT retry on:
        - 401/403 (auth errors)
        - 400 (client errors like invalid schema)

        Args:
            session: aiohttp session
            url: API endpoint URL
            headers: Request headers
            payload: Request payload
            attempt: Current attempt number

        Returns:
            Parsed JSON response

        Raises:
            ProviderAuthError: For 401/403 errors
            ProviderRateLimitError: For 429 after retries exhausted
            ProviderConnectionError: For other failures
        """
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                # Auth errors - no retry
                if response.status in (401, 403):
                    error_text = await response.text()
                    raise ProviderAuthError(
                        f"Authentication failed (HTTP {response.status}): {error_text}"
                    )

                # Client errors (except rate limit) - no retry
                if response.status == 400:
                    error_text = await response.text()
                    raise ProviderConnectionError(
                        f"Invalid request (HTTP 400): {error_text}"
                    )

                # Rate limit - retry with backoff
                if response.status == 429:
                    if attempt < self.MAX_RETRY_ATTEMPTS:
                        delay = self.INITIAL_RETRY_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            f"Rate limited (429), retrying in {delay}s "
                            f"(attempt {attempt}/{self.MAX_RETRY_ATTEMPTS})"
                        )
                        await asyncio.sleep(delay)
                        return await self._retry_request(
                            session, url, headers, payload, attempt + 1
                        )
                    else:
                        raise ProviderRateLimitError(
                            f"Rate limit exceeded after {self.MAX_RETRY_ATTEMPTS} attempts"
                        )

                # Server errors - retry with backoff
                if response.status >= 500:
                    if attempt < self.MAX_RETRY_ATTEMPTS:
                        delay = self.INITIAL_RETRY_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            f"Server error ({response.status}), retrying in {delay}s "
                            f"(attempt {attempt}/{self.MAX_RETRY_ATTEMPTS})"
                        )
                        await asyncio.sleep(delay)
                        return await self._retry_request(
                            session, url, headers, payload, attempt + 1
                        )
                    else:
                        error_text = await response.text()
                        raise ProviderConnectionError(
                            f"Server error after {self.MAX_RETRY_ATTEMPTS} attempts: "
                            f"HTTP {response.status}: {error_text}"
                        )

                # Success
                if response.status == 200:
                    return await response.json()

                # Other errors
                error_text = await response.text()
                raise ProviderConnectionError(
                    f"API error {response.status}: {error_text}"
                )

        except asyncio.TimeoutError:
            if attempt < self.MAX_RETRY_ATTEMPTS:
                delay = self.INITIAL_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Request timeout, retrying in {delay}s "
                    f"(attempt {attempt}/{self.MAX_RETRY_ATTEMPTS})"
                )
                await asyncio.sleep(delay)
                return await self._retry_request(
                    session, url, headers, payload, attempt + 1
                )
            else:
                raise ProviderConnectionError(
                    f"Request timeout after {self.MAX_RETRY_ATTEMPTS} attempts"
                )

        except aiohttp.ClientError as e:
            if attempt < self.MAX_RETRY_ATTEMPTS:
                delay = self.INITIAL_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Connection error: {e}, retrying in {delay}s "
                    f"(attempt {attempt}/{self.MAX_RETRY_ATTEMPTS})"
                )
                await asyncio.sleep(delay)
                return await self._retry_request(
                    session, url, headers, payload, attempt + 1
                )
            else:
                raise ProviderConnectionError(
                    f"Connection failed after {self.MAX_RETRY_ATTEMPTS} attempts: {str(e)}"
                )

    async def generate(self, request: ChatRequest) -> ChatResponse:
        """
        Generate a completion using GitHub Models API.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            ChatResponse with model output

        Raises:
            ProviderAuthError: If authentication fails
            ProviderRateLimitError: If rate limited
            ProviderConnectionError: If request fails
        """
        session = await self._get_session()
        url = self._build_endpoint()
        headers = self._build_headers()

        # Check for response_format in extra
        response_format = request.extra.get("response_format")
        payload = self._build_payload(request, response_format)

        try:
            data = await self._retry_request(session, url, headers, payload)
            return self._parse_response(data, request.model)
        except Exception as e:
            logger.error(f"Generate request failed: {str(e)}")
            raise

    async def generate_stream(self, request: ChatRequest):
        """
        Generate a streaming completion.

        Note: Streaming not yet implemented for GitHub Models.
        Falls back to non-streaming for now.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            String tokens as they become available
        """
        # For now, fall back to non-streaming
        response = await self.generate(request)
        yield response.content

    async def get_models(self) -> List[ModelInfo]:
        """
        Get list of available GitHub Models.

        Returns:
            List of ModelInfo instances
        """
        return self.GITHUB_MODELS

    async def health_check(self) -> bool:
        """
        Check if GitHub Models API is accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            session = await self._get_session()
            # Try a minimal request to check connectivity
            url = self._build_endpoint()
            headers = self._build_headers()

            # Simple test payload
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 5,
            }

            timeout = aiohttp.ClientTimeout(total=5)
            async with session.post(
                url, json=payload, headers=headers, timeout=timeout
            ) as response:
                # Health check passes if we don't get auth errors
                return response.status in (200, 429)  # 429 means API is up but rate limited

        except Exception as e:
            logger.warning(f"GitHub Models health check failed: {str(e)}")
            return False
