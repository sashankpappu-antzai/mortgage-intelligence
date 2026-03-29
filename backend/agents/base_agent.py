"""Base agent — abstract class all agents in mortgage-intelligence must extend."""

import abc
import functools
from typing import Any

from langfuse import Langfuse

from langchain_core.runnables import Runnable


from ..core.config import get_settings

settings = get_settings()

_langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)


def _traced(fn):
    """Decorator that wraps an async method in a Langfuse trace."""

    @functools.wraps(fn)
    async def wrapper(self: "BaseAgent", input: str, session_id: str, **kwargs) -> Any:
        trace = _langfuse.trace(
            name=f"{self.__class__.__name__}.run",
            session_id=session_id,
            input=input,
        )
        try:
            result = await fn(self, input, session_id, **kwargs)
            trace.update(output=str(result))
            return result
        except Exception as exc:
            trace.update(output=f"ERROR: {exc}", level="ERROR")
            raise

    return wrapper


class BaseAgent(abc.ABC):
    """Abstract base class for all agents in mortgage-intelligence."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Automatically wrap run() in Langfuse tracing for every subclass
        if "run" in cls.__dict__:
            cls.run = _traced(cls.__dict__["run"])

    @abc.abstractmethod
    async def run(self, input: str, session_id: str) -> Any:
        """Execute the agent with the given input and session ID."""
        ...
