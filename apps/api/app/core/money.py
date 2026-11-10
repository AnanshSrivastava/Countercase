"""Minor-unit money formatting for evidence summaries."""

ZERO_DECIMAL = {"jpy", "krw", "vnd", "clp", "isk", "ugx", "xof", "xaf"}
SYMBOLS = {"usd": "$", "eur": "€", "gbp": "£", "inr": "₹"}


def format_money(amount_minor: int, currency: str) -> str:
    cur = currency.lower()
    divisor = 1 if cur in ZERO_DECIMAL else 100
    symbol = SYMBOLS.get(cur)
    value = f"{amount_minor / divisor:,.{0 if divisor == 1 else 2}f}"
    return f"{symbol}{value}" if symbol else f"{value} {cur.upper()}"
