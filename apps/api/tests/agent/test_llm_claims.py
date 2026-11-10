import json

import httpx

from app.agent.llm_claims import llm_claims
from app.settings import settings

DISPUTE = {"category": "not_received", "reason_raw": "X", "amount": 100, "currency": "usd"}
EVIDENCE = [
    {"id": "ev_1", "type": "order_receipt", "summary": "Order ord_1, paid", "verified": True},
    {"id": "ev_2", "type": "seller_note", "summary": "He said so", "verified": False},
]


def client(reply: str, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "k"
        body = json.loads(request.content)
        assert (
            "ev_2" not in body["messages"][0]["content"]
        )  # unverified evidence never reaches the model
        return httpx.Response(status, json={"content": [{"type": "text", "text": reply}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def configure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "llm_model_draft", "m")


def test_model_claims_are_kept_only_when_they_cite_verified_evidence(monkeypatch) -> None:
    configure(monkeypatch)
    reply = json.dumps(
        [
            {"text": "The order was paid.", "evidence_id": "ev_1"},
            {"text": "Invented fact.", "evidence_id": "ev_999"},
            {"text": "Unverified.", "evidence_id": "ev_2"},
        ]
    )
    assert llm_claims(DISPUTE, EVIDENCE, [], http=client(reply)) == [
        {"text": "The order was paid.", "evidence_id": "ev_1"}
    ]


def test_falls_back_to_templates_on_failure_or_no_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "")
    templated = llm_claims(DISPUTE, EVIDENCE, [])
    assert templated and all(c["evidence_id"] == "ev_1" for c in templated)
    configure(monkeypatch)
    assert llm_claims(DISPUTE, EVIDENCE, [], http=client("not json at all")) == templated
    assert llm_claims(DISPUTE, EVIDENCE, [], http=client("[]", status=500)) == templated
