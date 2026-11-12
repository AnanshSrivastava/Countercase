"""Thin PayPal REST client (sandbox only).

Sync httpx, because the API calls it from worker threads (run_in_threadpool). A `transport` can be
injected so tests never touch the network. Errors surface as PayPalError carrying PayPal's own
`name` / issue code so callers can map by code, never by parsing prose.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

from app.settings import settings

log = logging.getLogger(__name__)

TOKEN_SKEW_SECONDS = 60


class PayPalError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _error_from(resp: httpx.Response) -> PayPalError:
    code, message = "paypal_error", resp.text[:300]
    try:
        body = resp.json()
        details = body.get("details") or []
        code = (details[0].get("issue") if details else None) or body.get("name") or code
        message = body.get("message") or message
    except ValueError:
        pass
    return PayPalError(code, message, resp.status_code)


class PayPalClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id = settings.paypal_client_id if client_id is None else client_id
        self.client_secret = (
            settings.paypal_client_secret if client_secret is None else client_secret
        )
        self.base_url = (base_url or settings.paypal_base_url).rstrip("/")
        self._http = httpx.Client(transport=transport, timeout=30.0)
        self._token: str | None = None
        self._token_expires = 0.0

    # -- availability ---------------------------------------------------------------------
    def available(self) -> tuple[bool, str]:
        """(True, "") when sandbox calls are possible. Live PayPal is never used."""
        if not self.client_id or not self.client_secret:
            return False, "no PayPal sandbox credentials are configured"
        host = urlparse(self.base_url).hostname or ""
        if "sandbox" not in host:
            return False, "only the PayPal sandbox is used; this base URL is not a sandbox"
        return True, ""

    # -- auth -------------------------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires:
            return self._token
        resp = self._http.post(
            f"{self.base_url}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise _error_from(resp)
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires = (
            time.monotonic() + int(body.get("expires_in", 300)) - TOKEN_SKEW_SECONDS
        )
        return self._token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", **kwargs.pop("headers", {})}
        resp = self._http.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        if resp.status_code == 401:  # token revoked early: refresh once
            self._token = None
            headers["Authorization"] = f"Bearer {self._access_token()}"
            resp = self._http.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise _error_from(resp)
        return resp.json() if resp.content else {}

    # -- disputes ---------------------------------------------------------------------------
    def get_dispute(self, dispute_id: str) -> dict:
        return self._request("GET", f"/v1/customer/disputes/{dispute_id}")

    def list_disputes(self, page_size: int = 20) -> list[dict]:
        body = self._request("GET", "/v1/customer/disputes", params={"page_size": page_size})
        return body.get("items", [])

    def provide_evidence(
        self,
        dispute_id: str,
        evidences: list[dict],
        files: dict[str, bytes],
        request_id: str,
    ) -> dict:
        """multipart/form-data: an `input` JSON part plus one part per document.

        Document parts are keyed by file name; the same name is listed in `documents`.
        """
        parts = {"input": (None, json.dumps({"evidences": evidences}), "application/json")}
        for name, data in files.items():
            parts[name] = (name, data, "application/pdf")
        return self._request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/provide-evidence",
            files=parts,
            headers={"PayPal-Request-Id": request_id},
        )

    def accept_claim(self, dispute_id: str, note: str, request_id: str) -> dict:
        return self._request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/accept-claim",
            json={"note": note, "accept_claim_reason": "REASON_NOT_SET"},
            headers={"PayPal-Request-Id": request_id},
        )

    # -- sandbox checkout ------------------------------------------------------------------
    def create_checkout_order(self) -> dict:
        """Create a fixed-value sandbox purchase used to exercise dispute workflows."""
        return self._request(
            "POST",
            "/v2/checkout/orders",
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "description": "Countercase Sandbox test purchase",
                        "amount": {"currency_code": "USD", "value": "10.00"},
                    }
                ],
            },
        )

    def capture_checkout_order(self, order_id: str) -> dict:
        """Capture a buyer-approved sandbox order."""
        return self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            json={},
        )

    # -- transactions -----------------------------------------------------------------------
    def get_transaction(self, transaction_id: str, around: datetime) -> dict | None:
        """Transaction Search needs a date window (max 31 days). Returns the one match or None."""
        start = (around - timedelta(days=30)).astimezone(UTC)
        end = around.astimezone(UTC) + timedelta(hours=1)
        body = self._request(
            "GET",
            "/v1/reporting/transactions",
            params={
                "transaction_id": transaction_id,
                "start_date": start.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "end_date": end.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "fields": "all",
            },
        )
        details = body.get("transaction_details") or []
        return details[0] if len(details) == 1 else None  # zero or several: never guess

    # -- webhooks ---------------------------------------------------------------------------
    def verify_webhook(self, headers: dict[str, str | None], raw_body: bytes) -> bool:
        """PayPal's own verify-webhook-signature call. The raw body is spliced in unchanged:
        re-serialising the event can alter it and break the signature."""
        needed = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
        }
        if not all(needed.values()):
            return False
        head = json.dumps({**needed, "webhook_id": settings.paypal_webhook_id})[:-1]
        body = f'{head}, "webhook_event": {raw_body.decode("utf-8")}}}'
        resp = self._http.post(
            f"{self.base_url}/v1/notifications/verify-webhook-signature",
            content=body.encode(),
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            raise _error_from(resp)
        return resp.json().get("verification_status") == "SUCCESS"
