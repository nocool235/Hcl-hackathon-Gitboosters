"""Small cleaning helpers used by the silver cleansing functions."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

NULL_TOKENS = {"", "na", "n/a", "null", "none", "nan"}
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
TRUE_VALUES = {"y", "yes", "true", "t", "1"}
FALSE_VALUES = {"n", "no", "false", "f", "0"}
CURRENCY_NOISE = re.compile("[₹$£€,\\s]|rs\\.?|inr", re.IGNORECASE)


def clean_text(value) -> str | None:
    """Strip whitespace and turn blank / NA-like tokens into None."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in NULL_TOKENS else text


def normalise_key(value) -> str | None:
    """Lowercase, '&' -> 'and', drop punctuation: 'In-store' -> 'instore'."""
    text = clean_text(value)
    if text is None:
        return None
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("&", "and"))


def map_value(value, mapping: dict[str, str]) -> str | None:
    key = normalise_key(value)
    return mapping.get(key) if key else None


def to_bool(value) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    if text.lower() in TRUE_VALUES:
        return 1
    if text.lower() in FALSE_VALUES:
        return 0
    return None


def parse_amount(value) -> Decimal | None:
    """'₹210,054.96' -> Decimal('210054.96'); anything unparseable -> None."""
    text = clean_text(value)
    if text is None:
        return None
    try:
        return Decimal(CURRENCY_NOISE.sub("", text))
    except InvalidOperation:
        return None


def _slash_parts(text: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def is_ambiguous_date(value) -> bool:
    """True for a slash date where both parts are <= 12 (could be DD/MM or MM/DD)."""
    text = clean_text(value)
    parts = _slash_parts(text) if text else None
    return bool(parts and parts[0] <= 12 and parts[1] <= 12 and parts[0] != parts[1])


def parse_date(value) -> str | None:
    """Return an ISO date string.

    Known formats: YYYY-MM-DD, DD-Mon-YYYY, and slash dates. A slash date with a first part
    above 12 must be DD/MM; with a second part above 12 must be MM/DD; if both parts are
    12 or below it is ambiguous and defaults to MM/DD (see docs/DECISIONS.md).
    """
    text = clean_text(value)
    if text is None:
        return None
    try:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        m = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", text)
        if m and m[2].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1])).isoformat()
        parts = _slash_parts(text)
        if parts:
            first, second, year = parts
            day, month = (first, second) if first > 12 else (second, first)
            return date(year, month, day).isoformat()
    except ValueError:
        return None
    return None


def clean_phone(value) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits or None


def money(value: Decimal | None) -> Decimal | None:
    """Keep monetary values exact through the database boundary."""
    return None if value is None else value.quantize(Decimal("0.01"))
