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

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


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
    elif provider in ("openai", "anthropic", "custom"):
        urls = {
            "openai": "https://api.openai.com",
            "anthropic": "https://api.anthropic.com",  # Needs compatible proxy
        }
        models = {
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-4-20250514",
        }
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
