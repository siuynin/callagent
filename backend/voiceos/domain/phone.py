"""Vietnamese phone normalization to E.164 (plan/docs/04, AC02).

Rules:
- Mobile national significant number (NSN): 9 digits starting with 3, 5, 7, 8 or 9.
- Landline NSN: 10 digits starting with 2 (area code 2xx + subscriber).
- Accepted prefixes: "+84", "84" (only when the rest is a valid NSN), "0".
- A bare NSN without a prefix (typical when a spreadsheet dropped the leading 0) is
  "uncertain": we never invent the missing digit, a human must review it.
"""

import re
from dataclasses import dataclass

_SEPARATORS = re.compile(r"[\s.\-()]")
_MOBILE_FIRST = "35789"


@dataclass(frozen=True)
class NormalizedPhone:
    status: str  # valid | invalid | uncertain
    e164: str | None
    reason: str | None = None


def _is_nsn(digits: str) -> bool:
    if len(digits) == 9 and digits[0] in _MOBILE_FIRST:
        return True
    return len(digits) == 10 and digits[0] == "2"


def normalize_vn_phone(raw: str) -> NormalizedPhone:
    text = _SEPARATORS.sub("", (raw or "").strip())
    if not text:
        return NormalizedPhone("invalid", None, "empty")

    plus = text.startswith("+")
    digits = text[1:] if plus else text
    if not digits.isdigit():
        return NormalizedPhone("invalid", None, "non_digit")

    if plus:
        if not digits.startswith("84"):
            return NormalizedPhone("invalid", None, "non_vn_country_code")
        nsn = digits[2:]
    elif digits.startswith("0"):
        nsn = digits[1:]
    elif digits.startswith("84") and _is_nsn(digits[2:]):
        nsn = digits[2:]
    elif _is_nsn(digits):
        return NormalizedPhone("uncertain", None, "missing_prefix_needs_review")
    else:
        return NormalizedPhone("invalid", None, "bad_length_or_prefix")

    if not _is_nsn(nsn):
        return NormalizedPhone("invalid", None, "bad_length_or_prefix")
    return NormalizedPhone("valid", "+84" + nsn)
