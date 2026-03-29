"""
Encompass API client with OAuth2 token management, rate limiting, and retry logic.
All Encompass interactions flow through this module.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class EncompassClient:
    """Centralized Encompass API client."""

    def __init__(
        self,
        instance_url: str,
        client_id: str,
        client_secret: str,
        webhook_secret: str = "",
    ):
        self.instance_url = instance_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.webhook_secret = webhook_secret

        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._token_lock = asyncio.Lock()

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self):
        await self._http.aclose()

    # --- Authentication ---

    async def _ensure_token(self) -> str:
        async with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 60:
                return self._access_token

            logger.info("Refreshing Encompass OAuth2 token")
            resp = await self._http.post(
                f"{self.instance_url}/oauth2/v1/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "lp",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            return self._access_token

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make authenticated request with retry logic."""
        token = await self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")

        url = f"{self.instance_url}{path}"

        for attempt in range(3):
            try:
                resp = await self._http.request(method, url, headers=headers, **kwargs)
                if resp.status_code == 401:
                    # Token expired, refresh and retry
                    self._access_token = None
                    token = await self._ensure_token()
                    headers["Authorization"] = f"Bearer {token}"
                    continue
                if resp.status_code == 429:
                    # Rate limited, back off
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"Encompass rate limited, retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.ConnectError:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError(f"Failed after 3 attempts: {method} {path}")

    # --- Loan Operations ---

    async def get_loan(self, loan_id: str) -> dict:
        resp = await self._request("GET", f"/encompass/v3/loans/{loan_id}")
        return resp.json()

    async def get_loan_fields(self, loan_id: str, field_ids: list[str]) -> dict:
        resp = await self._request(
            "POST",
            f"/encompass/v3/loans/{loan_id}/fieldReader",
            json=field_ids,
        )
        return resp.json()

    async def update_loan_fields(self, loan_id: str, fields: dict) -> dict:
        resp = await self._request(
            "PATCH",
            f"/encompass/v3/loans/{loan_id}",
            json=fields,
        )
        return resp.json()

    # --- eFolder / Document Operations ---

    async def list_documents(self, loan_id: str) -> list[dict]:
        resp = await self._request("GET", f"/encompass/v3/loans/{loan_id}/documents")
        return resp.json()

    async def create_document(self, loan_id: str, title: str, category: str) -> dict:
        resp = await self._request(
            "POST",
            f"/encompass/v3/loans/{loan_id}/documents",
            json={"title": title, "description": category, "applicationIndex": 0},
        )
        return resp.json()

    async def upload_attachment(self, loan_id: str, document_id: str, file_data: bytes, filename: str) -> dict:
        resp = await self._request(
            "PATCH",
            f"/encompass/v3/loans/{loan_id}/documents/{document_id}/attachments",
            content=file_data,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
        return resp.json()

    async def download_attachment(self, loan_id: str, attachment_id: str) -> bytes:
        resp = await self._request(
            "GET",
            f"/encompass/v3/loans/{loan_id}/attachments/{attachment_id}",
        )
        return resp.content

    # --- Conditions ---

    async def list_conditions(self, loan_id: str) -> list[dict]:
        resp = await self._request("GET", f"/encompass/v3/loans/{loan_id}/conditions")
        return resp.json()

    async def update_condition(self, loan_id: str, condition_id: str, updates: dict) -> dict:
        resp = await self._request(
            "PATCH",
            f"/encompass/v3/loans/{loan_id}/conditions/{condition_id}",
            json=updates,
        )
        return resp.json()

    async def link_document_to_condition(self, loan_id: str, condition_id: str, document_id: str) -> None:
        await self._request(
            "PUT",
            f"/encompass/v3/loans/{loan_id}/conditions/{condition_id}/documents",
            json=[{"documentId": document_id}],
        )

    # --- Milestones ---

    async def get_milestones(self, loan_id: str) -> list[dict]:
        resp = await self._request("GET", f"/encompass/v3/loans/{loan_id}/milestones")
        return resp.json()

    async def update_milestone(self, loan_id: str, milestone_id: str, updates: dict) -> dict:
        resp = await self._request(
            "PATCH",
            f"/encompass/v3/loans/{loan_id}/milestones/{milestone_id}",
            json=updates,
        )
        return resp.json()

    # --- Pipeline ---

    async def query_pipeline(self, filters: dict, fields: list[str] | None = None) -> list[dict]:
        body: dict[str, Any] = {"filter": filters}
        if fields:
            body["fields"] = fields
        resp = await self._request("POST", "/encompass/v3/loans/pipeline", json=body)
        return resp.json()

    # --- Services ---

    async def order_credit(self, loan_id: str, provider: str = "CoreLogic") -> dict:
        resp = await self._request(
            "POST",
            f"/encompass/v3/loans/{loan_id}/services/credit",
            json={"provider": provider},
        )
        return resp.json()

    async def submit_to_aus(self, loan_id: str, aus_type: str = "DU") -> dict:
        resp = await self._request(
            "POST",
            f"/encompass/v3/loans/{loan_id}/services/aus",
            json={"ausType": aus_type},
        )
        return resp.json()

    # --- Webhook Verification ---

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Encompass webhook HMAC-SHA256 signature."""
        if not self.webhook_secret:
            logger.warning("No webhook secret configured, skipping verification")
            return True

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
