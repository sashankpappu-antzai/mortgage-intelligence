"""
Open-source LLM provider abstraction.
Supports fully self-hosted options (Ollama, vLLM) and optional cloud APIs (OpenAI, Anthropic).
Default: Ollama (runs locally, no API keys needed, fully open-source).

Provider options:
  - ollama:    Local models via Ollama (default, open-source, no API key)
  - vllm:      Self-hosted vLLM server (open-source, no API key)
  - litellm:   Proxy that unifies 100+ providers behind OpenAI-compatible API (open-source)
  - openai:    OpenAI API (optional, requires API key)
  - anthropic: Anthropic Claude API (optional, requires API key)
"""

import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Retry settings for rate-limit (429) and transient server errors (5xx)
_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 2.0   # 2s, 4s, 8s, 16s, 32s
_MAX_DELAY_SECONDS = 60.0
_JITTER_FACTOR = 0.5  # ±50% random jitter to de-synchronize retries


@dataclass
class LLMMessage:
    role: str  # system, user, assistant
    content: str | list[dict]  # str for text, list for multimodal (images)


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract LLM interface. All providers implement this."""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a chat completion request."""
        ...

    @abstractmethod
    async def chat_with_vision(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion with image inputs (for document OCR)."""
        ...

    async def close(self):
        """Cleanup resources."""
        pass


class OllamaProvider(LLMProvider):
    """
    Ollama - run open-source LLMs locally.
    Install: https://ollama.ai
    Models: llama3.1, mistral, mixtral, llava (vision), codellama, etc.
    No API key needed. Fully open-source. MIT license.
    """

    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "llama3.1"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.default_model
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"

        resp = await self._http.post(f"{self.base_url}/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()

        return LLMResponse(
            content=data["message"]["content"],
            model=model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            raw=data,
        )

    async def chat_with_vision(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Ollama supports vision via llava, llama3.2-vision, etc.
        model = model or "llava"
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    async def close(self):
        await self._http.aclose()


class VLLMProvider(LLMProvider):
    """
    vLLM - high-throughput self-hosted inference server.
    Install: pip install vllm
    Exposes OpenAI-compatible API. Apache 2.0 license.
    """

    def __init__(self, base_url: str = "http://localhost:8080", default_model: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.default_model
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        resp = await self._http.post(f"{self.base_url}/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]

        return LLMResponse(
            content=choice["message"]["content"],
            model=model,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def chat_with_vision(self, messages, model=None, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    async def close(self):
        await self._http.aclose()


class LiteLLMProvider(LLMProvider):
    """
    LiteLLM - open-source proxy that provides OpenAI-compatible API
    for 100+ LLM providers (Ollama, HuggingFace, Bedrock, Vertex, etc.)
    Install: pip install litellm
    MIT license.
    """

    def __init__(self, base_url: str = "http://localhost:4000", default_model: str = "ollama/llama3.1", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        self._api_key = api_key

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.default_model
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        resp = await self._http.post(f"{self.base_url}/v1/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]

        return LLMResponse(
            content=choice["message"]["content"],
            model=model,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def chat_with_vision(self, messages, model=None, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    async def close(self):
        await self._http.aclose()


class OpenAICompatibleProvider(LLMProvider):
    """
    Generic OpenAI-compatible API provider.
    Works with: OpenAI, Anthropic (via proxy), Azure OpenAI, Together AI,
    Groq, Fireworks, Mistral API, any OpenAI-compatible endpoint.
    """

    def __init__(self, base_url: str, api_key: str, default_model: str):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.default_model
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        resp = await self._http.post(f"{self.base_url}/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]

        return LLMResponse(
            content=choice["message"]["content"],
            model=model,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def chat_with_vision(self, messages, model=None, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    async def close(self):
        await self._http.aclose()


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude API using the native anthropic SDK.
    Supports text + vision (claude-sonnet-4-6, claude-opus-4-6).
    Requires ANTHROPIC_API_KEY.

    Includes automatic retry with exponential backoff for:
      - 429 Rate Limit errors (respects Retry-After header)
      - 529 Overloaded errors
      - 500/502/503 transient server errors
    """

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-6"):
        import anthropic as _anthropic
        self._anthropic_module = _anthropic
        self._client = _anthropic.AsyncAnthropic(api_key=api_key)
        self.default_model = default_model

    def _is_retryable(self, exc: Exception) -> bool:
        """Check if an Anthropic SDK exception is retryable (rate limit or transient)."""
        anthropic = self._anthropic_module

        # Rate limit — always retry
        if isinstance(exc, anthropic.RateLimitError):
            return True

        # Overloaded (529) — retry
        if isinstance(exc, anthropic.APIStatusError) and getattr(exc, "status_code", 0) == 529:
            return True

        # Transient server errors (500, 502, 503)
        if isinstance(exc, anthropic.InternalServerError):
            return True

        return False

    def _get_retry_after(self, exc: Exception) -> float | None:
        """Extract Retry-After header from an API error response, if present."""
        response = getattr(exc, "response", None)
        if response is not None:
            retry_after = getattr(response, "headers", {}).get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass
        return None

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.default_model
        system_parts = [m.content for m in messages if m.role == "system" and isinstance(m.content, str)]
        system = "\n".join(system_parts)
        if json_mode:
            system += "\n\nYou must respond with valid JSON only. No markdown, no explanation, just the JSON object."

        filtered = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=filtered)
        if system:
            kwargs["system"] = system

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):  # attempt 0 = first try, then up to _MAX_RETRIES retries
            try:
                resp = await self._client.messages.create(**kwargs)
                content = resp.content[0].text if resp.content else ""
                return LLMResponse(
                    content=content,
                    model=model,
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    finish_reason=resp.stop_reason or "stop",
                )
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable(exc) or attempt == _MAX_RETRIES:
                    raise

                # Compute delay: honour Retry-After header, else exponential backoff + jitter
                retry_after = self._get_retry_after(exc)
                if retry_after and retry_after > 0:
                    delay = min(retry_after, _MAX_DELAY_SECONDS)
                else:
                    base = _BASE_DELAY_SECONDS * (2 ** attempt)
                    jitter = base * _JITTER_FACTOR * (2 * random.random() - 1)
                    delay = min(base + jitter, _MAX_DELAY_SECONDS)

                logger.warning(
                    "Anthropic API %s (attempt %d/%d), retrying in %.1fs: %s",
                    type(exc).__name__,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    delay,
                    str(exc)[:200],
                )
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise last_exc  # type: ignore[misc]

    async def chat_with_vision(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Vision content is already embedded in message content as list[dict]
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)


def create_llm(
    provider: str = "ollama",
    base_url: str = "",
    api_key: str = "",
    default_model: str = "",
) -> LLMProvider:
    """
    Factory function to create the configured LLM provider.

    Fully open-source options (no API key needed):
      - ollama:  Local models (default). Install ollama, run `ollama pull llama3.1`
      - vllm:    Self-hosted vLLM server
      - litellm: Open-source proxy for any backend

    Optional cloud APIs (require API key):
      - openai:    OpenAI API
      - anthropic: Via OpenAI-compatible proxy
      - custom:    Any OpenAI-compatible endpoint
    """
    if provider == "ollama":
        return OllamaProvider(
            base_url=base_url or "http://localhost:11434",
            default_model=default_model or "llama3.1",
        )
    elif provider == "vllm":
        return VLLMProvider(
            base_url=base_url or "http://localhost:8080",
            default_model=default_model or "default",
        )
    elif provider == "litellm":
        return LiteLLMProvider(
            base_url=base_url or "http://localhost:4000",
            default_model=default_model or "ollama/llama3.1",
            api_key=api_key,
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            api_key=api_key,
            default_model=default_model or "claude-sonnet-4-6",
        )
    elif provider in ("openai", "custom"):
        urls = {"openai": "https://api.openai.com"}
        models = {"openai": "gpt-4o"}
        return OpenAICompatibleProvider(
            base_url=base_url or urls.get(provider, base_url),
            api_key=api_key,
            default_model=default_model or models.get(provider, default_model),
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Open-source: ollama, vllm, litellm. "
            f"Cloud (optional): openai, anthropic, custom"
        )
