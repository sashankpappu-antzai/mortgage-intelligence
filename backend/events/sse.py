"""Server-Sent Events (SSE) for real-time dashboard updates.

Process-local pub/sub keyed by (channel-type, tenant_id).  Subscribers receive
ONLY events whose loan belongs to their tenant.  Replace with Redis pub/sub
once the API runs on multiple replicas (improvements.md §10).
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

from sqlalchemy import select

from ..db.models.loan import Loan
from ..db.postgres import get_db_session

logger = logging.getLogger(__name__)

# Channel key = "loan:{tenant_id}:{loan_id}"  or  "pipeline:{tenant_id}"
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

_KEEPALIVE_SECONDS = 15


async def _resolve_tenant_id(loan_id: str) -> str | None:
    """Cheap DB lookup for the tenant of a given loan.  Used by publishers that
    don't already have a tenant in scope (background tasks, agents)."""
    try:
        async with get_db_session() as db:
            result = await db.execute(select(Loan.tenant_id).where(Loan.id == loan_id))
            row = result.scalar_one_or_none()
            return str(row) if row else None
    except Exception:
        logger.exception("Failed to resolve tenant for loan %s", loan_id)
        return None


async def broadcast_loan_event(
    loan_id: str,
    event_type: str,
    data: dict,
    *,
    tenant_id: str | None = None,
) -> None:
    """Broadcast an event to all subscribers watching a specific loan.

    If `tenant_id` is None, it is resolved from the database — pass it
    explicitly from a router that already has `user.tenant_id` to avoid the
    extra query.
    """
    if tenant_id is None:
        tenant_id = await _resolve_tenant_id(loan_id)
        if tenant_id is None:
            logger.warning("Dropping SSE event for unknown loan_id=%s", loan_id)
            return

    message = json.dumps({"loan_id": loan_id, "event": event_type, "data": data})

    loan_key = f"loan:{tenant_id}:{loan_id}"
    pipeline_key = f"pipeline:{tenant_id}"

    for queue in _subscribers.get(loan_key, []):
        await queue.put(message)
    for queue in _subscribers.get(pipeline_key, []):
        await queue.put(message)


async def _stream(key: str) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[key].append(queue)
    try:
        while True:
            try:
                # Keepalive so proxies (Render's edge, nginx) don't reap the connection.
                message = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        try:
            _subscribers[key].remove(queue)
        except ValueError:
            pass


def subscribe_loan(tenant_id: str, loan_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to events for a specific loan, scoped to the tenant.
    Caller must have already verified that `loan_id` belongs to `tenant_id`."""
    return _stream(f"loan:{tenant_id}:{loan_id}")


def subscribe_pipeline(tenant_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to all pipeline events for a single tenant."""
    return _stream(f"pipeline:{tenant_id}")
