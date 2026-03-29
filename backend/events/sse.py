"""
Server-Sent Events (SSE) for real-time dashboard updates.
Uses Redis pub/sub as the message broker.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# In-memory subscribers (per-process). In production, use Redis pub/sub.
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def broadcast_loan_event(loan_id: str, event_type: str, data: dict) -> None:
    """Broadcast an event to all subscribers watching a specific loan."""
    message = json.dumps({"loan_id": loan_id, "event": event_type, "data": data})

    # Broadcast to loan-specific subscribers
    for queue in _subscribers.get(f"loan:{loan_id}", []):
        await queue.put(message)

    # Broadcast to pipeline-level subscribers (UW dashboard)
    for queue in _subscribers.get("pipeline", []):
        await queue.put(message)


async def subscribe_loan(loan_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to events for a specific loan. Yields SSE-formatted strings."""
    queue: asyncio.Queue = asyncio.Queue()
    key = f"loan:{loan_id}"
    _subscribers[key].append(queue)
    try:
        while True:
            message = await queue.get()
            yield f"data: {message}\n\n"
    finally:
        _subscribers[key].remove(queue)


async def subscribe_pipeline() -> AsyncGenerator[str, None]:
    """Subscribe to all pipeline events (for UW dashboard). Yields SSE-formatted strings."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers["pipeline"].append(queue)
    try:
        while True:
            message = await queue.get()
            yield f"data: {message}\n\n"
    finally:
        _subscribers["pipeline"].remove(queue)
