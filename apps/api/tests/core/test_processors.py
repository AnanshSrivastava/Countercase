"""StripeSubmitter against a fake Stripe client: asserts the exact calls it would make.

This is the strongest proof available without a Stripe key. The real calls are untested.
"""

import io
from types import SimpleNamespace

import pytest
import stripe

from app.core import processors
from app.core.processors import PAGE_LIMIT_CODE, StripeSubmitter, SubmitError


class FakeStripe:
    """Mimics the parts of stripe.StripeClient(...).v1 that the adapter uses."""

    def __init__(self, *, update_error=None, retrieve=None, close_error=None) -> None:
        self.calls: list[tuple] = []
        self.update_error, self.close_error = update_error, close_error
        self.retrieved = retrieve or {"evidence_details": {"submission_count": 0}}
        outer = self

        class Files:
            def create(self, params, options=None):
                outer.calls.append(("files.create", params, options))
                return SimpleNamespace(id="file_123")

        class Disputes:
            def update(self, dispute, params=None, options=None):
                outer.calls.append(("disputes.update", dispute, params, options))
                if outer.update_error:
                    raise outer.update_error
                return SimpleNamespace(id=dispute)

            def retrieve(self, dispute, params=None, options=None):
                outer.calls.append(("disputes.retrieve", dispute))
                return SimpleNamespace(to_dict=lambda: outer.retrieved)

            def close(self, dispute, params=None, options=None):
                outer.calls.append(("disputes.close", dispute))
                if outer.close_error:
                    raise outer.close_error

        self.v1 = SimpleNamespace(files=Files(), disputes=Disputes())


@pytest.fixture
def fake(monkeypatch):
    holder = {}

    def factory(key, **kwargs):
        holder["key"], holder["kwargs"] = key, kwargs
        return holder["client"]

    monkeypatch.setattr(processors.stripe, "StripeClient", factory)

    def install(client: FakeStripe) -> FakeStripe:
        holder["client"] = client
        return client

    install.holder = holder
    return install


def submit(sub: StripeSubmitter) -> None:
    sub.submit(
        processor_dispute_id="du_123",
        idempotency_key="sub_abc",
        letter_text="the letter",
        packet_pdf=b"%PDF-fake",
        shipping_carrier="CourierX",
    )


def test_submit_uploads_a_fresh_file_then_submits_with_idempotency_keys(fake) -> None:
    client = fake(FakeStripe())
    submit(StripeSubmitter("sk_test_abc"))

    (upload, update) = client.calls
    assert upload[0] == "files.create"
    assert upload[1]["purpose"] == "dispute_evidence"
    assert (
        isinstance(upload[1]["file"], io.BytesIO) and upload[1]["file"].getvalue() == b"%PDF-fake"
    )
    assert upload[2] == {"idempotency_key": "sub_abc:file"}

    assert update[0:2] == ("disputes.update", "du_123")
    assert update[2] == {
        "evidence": {
            "uncategorized_file": "file_123",
            "uncategorized_text": "the letter",
            "shipping_carrier": "CourierX",
        },
        "submit": True,
    }
    assert update[3] == {"idempotency_key": "sub_abc"}
    assert fake.holder["key"] == "sk_test_abc"
    assert fake.holder["kwargs"] == {"max_network_retries": 2}


def test_carrier_is_omitted_when_unknown(fake) -> None:
    client = fake(FakeStripe())
    StripeSubmitter("sk_test_abc").submit(
        processor_dispute_id="du_1",
        idempotency_key="k",
        letter_text="t",
        packet_pdf=b"x",
        shipping_carrier=None,
    )
    assert "shipping_carrier" not in client.calls[1][2]["evidence"]


def test_page_limit_error_is_mapped_by_code_not_message(fake) -> None:
    err = stripe.InvalidRequestError("totally different wording", "evidence", code=PAGE_LIMIT_CODE)
    fake(FakeStripe(update_error=err))
    with pytest.raises(SubmitError) as exc:
        submit(StripeSubmitter("sk_test_abc"))
    assert exc.value.code == PAGE_LIMIT_CODE
    assert "Remove an attachment" in exc.value.message


def test_other_stripe_errors_keep_their_code(fake) -> None:
    err = stripe.InvalidRequestError("No such dispute", "dispute", code="resource_missing")
    fake(FakeStripe(update_error=err))
    with pytest.raises(SubmitError) as exc:
        submit(StripeSubmitter("sk_test_abc"))
    assert exc.value.code == "resource_missing"


def test_is_submitted_reads_the_submission_count(fake) -> None:
    fake(FakeStripe(retrieve={"evidence_details": {"submission_count": 1}}))
    assert StripeSubmitter("sk_test_abc").is_submitted("du_1") is True
    fake(FakeStripe(retrieve={"evidence_details": {"submission_count": 0}}))
    assert StripeSubmitter("sk_test_abc").is_submitted("du_1") is False
    fake(FakeStripe(retrieve={}))
    assert StripeSubmitter("sk_test_abc").is_submitted("du_1") is False


def test_close_accepts_the_dispute(fake) -> None:
    client = fake(FakeStripe())
    StripeSubmitter("sk_test_abc").close("du_9")
    assert client.calls == [("disputes.close", "du_9")]


def test_close_error_is_mapped(fake) -> None:
    fake(FakeStripe(close_error=stripe.InvalidRequestError("gone", "d", code="resource_missing")))
    with pytest.raises(SubmitError) as exc:
        StripeSubmitter("sk_test_abc").close("du_9")
    assert exc.value.code == "resource_missing"


@pytest.mark.parametrize(
    ("key", "ok"),
    [
        ("sk_test_abc123", True),
        ("rk_test_abc123", True),
        ("sk_test_xxx", False),  # the .env.example placeholder
        ("", False),
        ("sk_live_abc123", False),  # live keys are never used
        ("rk_live_abc123", False),
        ("pk_test_abc123", False),  # publishable keys cannot do this either
    ],
)
def test_only_test_keys_are_available(key, ok) -> None:
    available, why = StripeSubmitter(key).available()
    assert available is ok
    assert ok or why
