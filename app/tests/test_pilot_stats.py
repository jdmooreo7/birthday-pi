from datetime import datetime, timedelta, timezone

from birthday_pi import cli, db, reminders

from tests.test_reminders import TODAY, _conn, _person


def _ack(conn, key, local):
    utc = local.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO reminder_acks (key, acked_at) VALUES (?, ?)", (key, utc))


def test_pilot_stats_counts_without_names(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    _person(conn, "Rosa", 0)   # call today, cleared at 2 pm; her card reminder last week was never cleared
    _person(conn, "Leo", 5)    # card showing now; its gift reminder ran last week and was never cleared
    rosa_call = reminders.active(conn, TODAY)[0].key
    _ack(conn, rosa_call, datetime(TODAY.year, TODAY.month, TODAY.day, 14))

    _ack(conn, f"p999:gift:{(TODAY + timedelta(days=30)).isoformat()}", datetime(TODAY.year, TODAY.month, TODAY.day, 9))

    out = "\n".join(cli.pilot_stats(conn, TODAY))
    assert "not counted: 1 cleared while testing with a pretend date" in out
    assert "Reminders cleared with Got it: 1 (1 on the day they appeared)" in out
    assert "median 14.0, longest 14.0" in out
    assert "Reminders showing now: 1" in out
    assert "Reminders that ended without Got it: 2" in out  # Rosa's card, Leo's gift
    assert "waiting for Grandma's OK: 0" in out
    assert "Rosa" not in out and "Leo" not in out


def test_pilot_stats_flags_a_pretend_date(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    db.set_setting(conn, "pretend_date", (TODAY + timedelta(days=3)).isoformat())
    assert cli.pilot_stats(conn, TODAY)[0].startswith("Note: a pretend date is on")
