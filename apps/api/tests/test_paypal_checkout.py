"""PayPal Orders v2 checkout calls stay server-side and use a fixed USD test amount."""

import json

import httpx

from app.core.paypal.client import PayPalClient


def test_create_checkout_order_uses_fixed_sandbox_purchase() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        return httpx.Response(201, json={"id": "TESTORDER123", "status": "CREATED"})

    client = PayPalClient(
        "sandbox-client",
        "sandbox-secret",
        "https://api-m.sandbox.paypal.com",
        transport=httpx.MockTransport(respond),
    )
    try:
        result = client.create_checkout_order()
    finally:
        client._http.close()

    order_request = requests[-1]
    body = json.loads(order_request.content)
    assert result["id"] == "TESTORDER123"
    assert order_request.method == "POST"
    assert order_request.url.path == "/v2/checkout/orders"
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "10.00"}


def test_capture_checkout_order_uses_order_id_path() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        return httpx.Response(
            201,
            json={"id": "TESTORDER123", "status": "COMPLETED"},
        )

    client = PayPalClient(
        "sandbox-client",
        "sandbox-secret",
        "https://api-m.sandbox.paypal.com",
        transport=httpx.MockTransport(respond),
    )
    try:
        result = client.capture_checkout_order("TESTORDER123")
    finally:
        client._http.close()

    capture_request = requests[-1]
    assert result["status"] == "COMPLETED"
    assert capture_request.method == "POST"
    assert capture_request.url.path == "/v2/checkout/orders/TESTORDER123/capture"
