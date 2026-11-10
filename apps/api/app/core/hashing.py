"""Per-seller salted customer hashes (IMPROVEMENTS #7). Repeat disputers are detectable inside one
seller's data, but hashes cannot be joined across sellers. Raw identifiers are never stored."""

import hashlib
import hmac

from app.settings import settings


def customer_hash(seller_id: str, identifier: str) -> str:
    normalized = identifier.strip().lower()
    digest = hmac.new(
        settings.customer_hash_salt.encode(),
        f"{seller_id}:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return "c_" + digest[:16]
