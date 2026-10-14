from datetime import date, timedelta

from birthday_pi import db, reminders

TODAY = date(2026, 10, 14)


def _conn(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    return db.connect()


def _person(conn, name, days, year=None):
    d = TODAY + timedelta(days=days)
    return conn.execute("INSERT INTO people (name, birth_month, birth_day, birth_year) VALUES (?, ?, ?, ?)",
                        (name, d.month, d.day, year)).lastrowid


def test_stages_and_wording(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    _person(conn, "Rosa", 0)
    _person(conn, "Leo", 7, 2016)
    _person(conn, "Mia", 14)
    _person(conn, "Too far", 15)
    rs = reminders.active(conn, TODAY)
    assert [(r.stage, r.headline) for r in rs] == [
        ("call", "It's Rosa's birthday"),
        ("card", "Leo's birthday is in 7 days"),
        ("gift", "Mia's birthday is in 2 weeks"),
    ]
    assert rs[1].sub == "Wednesday, October 21 · turns 10"


def test_text_grows_daily_to_a_maximum(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    _person(conn, "Mia", 14)
    sizes = [reminders.active(conn, TODAY + timedelta(days=n))[0].size_px for n in range(7)]
    assert sizes == [64, 80, 96, 112, 128, 144, 160]
    card = reminders.active(conn, TODAY + timedelta(days=7))[0]
    assert card.stage == "card" and card.size_px == 96
    call = reminders.active(conn, TODAY + timedelta(days=14))[0]
    assert call.stage == "call" and call.size_px == 160


def test_got_it_clears_only_that_stage(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    _person(conn, "Mia", 10)
    gift = reminders.active(conn, TODAY)[0]
    reminders.acknowledge(conn, gift.key, None)
    assert reminders.active(conn, TODAY) == []
    assert reminders.active(conn, TODAY + timedelta(days=3))[0].stage == "card"


def test_stack_fits_the_monitor():
    def r(px):
        return reminders.Reminder("k", "gift", "", "", "", TODAY, 1, px)
    assert reminders.monitor_sizes([r(160)]) == [160]
    assert reminders.monitor_sizes([r(160), r(64)]) == [112, 64]
    assert reminders.monitor_sizes([r(160)] * 5) == [88, 88, 88]  # only 3 shown


def test_anniversary_wording(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    pid = _person(conn, "Dana", 100)
    d = TODAY + timedelta(days=3)
    conn.execute("INSERT INTO anniversaries (person_id, kind, month, day, year) VALUES (?, 'wedding', ?, ?, 2013)",
                 (pid, d.month, d.day))
    r = reminders.active(conn, TODAY)[0]
    assert r.headline == "Dana's wedding anniversary is in 3 days" and r.sub.endswith("· 13 years")
