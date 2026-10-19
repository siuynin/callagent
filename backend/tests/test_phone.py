import pytest

from voiceos.domain.phone import normalize_vn_phone


@pytest.mark.parametrize(
    "raw,e164",
    [
        ("0900000001", "+84900000001"),
        ("+84900000001", "+84900000001"),
        ("84900000001", "+84900000001"),
        ("090 000 0001", "+84900000001"),
        ("090.000.0001", "+84900000001"),
        ("(0269) 382 1234", "+842693821234"),  # landline, area code 269
        ("0369000000", "+84369000000"),
    ],
)
def test_valid(raw, e164):
    r = normalize_vn_phone(raw)
    assert r.status == "valid" and r.e164 == e164


@pytest.mark.parametrize("raw", ["12345", "", "abc", "+1 415 555 0100", "0100000000", "09000000011"])
def test_invalid(raw):
    r = normalize_vn_phone(raw)
    assert r.status == "invalid" and r.e164 is None


def test_lost_leading_zero_is_not_invented():
    # spreadsheet turned 0900000001 into a number: never guess the missing digit (plan/docs/04)
    r = normalize_vn_phone("900000001")
    assert r.status == "uncertain" and r.e164 is None


def test_fixture_duplicate_normalizes_equal():
    # plan/examples/sheets-import.csv rows DEMO-001 and DEMO-003
    assert normalize_vn_phone("0900000001").e164 == normalize_vn_phone("+84900000001").e164
