from birthday_pi import db, pins


def test_pin_check_and_lockout(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    conn = db.connect()
    pins.set_pin(conn, "1234")
    assert pins.check_pin(conn, "1234", now=0) == "ok"
    for _ in range(pins.MAX_TRIES):
        assert pins.check_pin(conn, "0000", now=0) == "wrong"
    assert pins.check_pin(conn, "1234", now=1) == "locked"
    assert pins.check_pin(conn, "1234", now=pins.LOCK_SECONDS + 1) == "ok"


def test_pin_is_not_stored_in_plain_text(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    conn = db.connect()
    pins.set_pin(conn, "1234")
    assert "1234" not in db.get_setting(conn, "pin_hash")


def test_only_four_digits_are_valid():
    assert pins.is_valid("0042")
    assert not pins.is_valid("123")
    assert not pins.is_valid("12345")
    assert not pins.is_valid("12a4")
