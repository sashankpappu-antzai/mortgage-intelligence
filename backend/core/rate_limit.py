"""Process-local IP-based rate limiter used for auth endpoints.

This is a `slowapi`-based middleware backed by in-memory counters.  Sufficient for
the single-pod trial deploy on Render; replace with Redis-backed storage once
the API runs on multiple replicas (see improvements.md §10).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# `key_func=get_remote_address` uses the client's IP.  When deployed behind a
# proxy (Render, Cloudflare) you must also enable a trusted-proxy middleware so
# `request.client.host` reflects the real client IP via X-Forwarded-For.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
