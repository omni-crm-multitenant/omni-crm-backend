from __future__ import annotations

import re


try:
    import phonenumbers
except ImportError:  # pragma: no cover - optional local fallback
    phonenumbers = None


def normalize_email(raw: str) -> str:
    value = raw.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("invalid email")
    return value


def normalize_phone(raw: str, default_region: str = "CO") -> str:
    value = raw.strip()
    if not value:
        raise ValueError("invalid phone")
    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(value, default_region)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("invalid phone") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("invalid phone")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    digits = re.sub(r"\D", "", value)
    if value.startswith("+") and len(digits) >= 8:
        return f"+{digits}"
    prefixes = {"CO": "57", "MX": "52", "US": "1", "CA": "1", "ES": "34"}
    prefix = prefixes.get(default_region.upper())
    if prefix is None or len(digits) < 8:
        raise ValueError("invalid phone")
    if default_region.upper() == "CO" and len(digits) == 10 and digits.startswith("3"):
        return f"+{prefix}{digits}"
    return f"+{prefix}{digits}"
