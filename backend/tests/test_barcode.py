from app.barcode import is_valid_length, normalize_barcode


def test_removes_non_digits():
    assert normalize_barcode("880-1118 001802") == "8801118001802"


def test_upca_12_digits_gets_leading_zero():
    assert normalize_barcode("012345678905") == "0012345678905"


def test_13_digits_unchanged():
    assert normalize_barcode("8801118001802") == "8801118001802"


def test_empty_and_none():
    assert normalize_barcode("") == ""
    assert normalize_barcode(None) == ""


def test_length_rules():
    assert is_valid_length("12345678")
    assert not is_valid_length("1234567")
    assert not is_valid_length("")
