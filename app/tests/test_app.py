from datetime import date, timedelta

from birthday_pi import cli, db


def test_fresh_pi_sends_phones_to_setup_and_monitor_shows_welcome(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/setup"
    screen = client.get("/screen").text
    assert "Let's meet your family." in screen
    assert "<svg" in screen  # QR code
    assert "birthdaypi.local:8080/setup" in screen


def test_setup_validates_pin(client):
    r = client.post("/setup", data={"owner_name": "Grandma", "pin": "12", "pin2": "12"})
    assert r.status_code == 400 and "exactly 4 numbers" in r.text
    r = client.post("/setup", data={"owner_name": "Grandma", "pin": "1234", "pin2": "4321"})
    assert r.status_code == 400 and "don&#39;t match" in r.text


def test_setup_then_pick_grandma_needs_pin(client):
    r = client.post("/setup", data={"owner_name": "Nana", "pin": "2468", "pin2": "2468"}, follow_redirects=False)
    assert r.headers["location"] == "/who"
    assert client.get("/setup", follow_redirects=False).headers["location"] == "/"
    who = client.get("/who").text
    assert "Nana" in who and "asks for PIN" in who
    owner_id = db.owner(db.connect())["id"]
    r = client.post("/who", data={"person_id": owner_id}, follow_redirects=False)
    assert r.headers["location"] == "/pin"
    assert client.get("/", follow_redirects=False).headers["location"] == "/who"  # not trusted yet
    r = client.post("/pin", data={"pin": "1111"})
    assert r.status_code == 400 and "isn&#39;t right" in r.text
    r = client.post("/pin", data={"pin": "2468"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    home = client.get("/").text
    assert "Nana" in home and "Let's add the family" in home


def test_someone_new_is_added_and_asked_for_birthday(set_up):
    client = set_up
    r = client.post("/who", data={"new_name": "Dana"}, follow_redirects=False)
    assert r.headers["location"].endswith("?welcome=1")
    page = client.get(r.headers["location"]).text
    assert "Hi Dana!" in page
    assert "Dana · " in client.get("/").text
    assert "2 people need a birthday" in client.get("/").text  # Dana and Grandma


def test_add_person_with_birthday_and_typed_anniversaries(set_up):
    client = set_up
    form = client.get("/people/new").text
    assert "Wedding" in form and "Graduation" in form and 'name="partner_id"' not in form
    r = client.post("/people/new", data={"name": "Dana", "birth_month": "7", "birth_day": "1", "ann_count": "1",
                                         "ann_0_kind": "wedding", "ann_0_month": "11", "ann_0_day": "9",
                                         "ann_0_year": "2013"}, follow_redirects=False)
    assert r.status_code == 303
    dana = db.connect().execute("SELECT id FROM people WHERE name = 'Dana'").fetchone()[0]
    edit = client.get(f"/people/{dana}").text
    assert 'name="ann_count" value="2"' in edit  # the saved one plus a blank row
    client.post(f"/people/{dana}", data={"name": "Dana", "birth_month": "7", "birth_day": "1", "ann_count": "2",
                                         "ann_0_kind": "wedding", "ann_0_month": "11", "ann_0_day": "9",
                                         "ann_1_kind": "graduation", "ann_1_month": "6", "ann_1_day": "1"})
    everyone = client.get("/people").text
    assert "Wedding anniversary · November 9" in everyone and "Graduation anniversary · June 1" in everyone
    # Setting the month to "–" removes it.
    client.post(f"/people/{dana}", data={"name": "Dana", "ann_count": "2", "ann_0_kind": "wedding",
                                         "ann_0_month": "11", "ann_0_day": "9", "ann_1_kind": "graduation"})
    assert "Graduation" not in client.get("/people").text


def test_coming_up_only_shows_next_60_days(set_up, monkeypatch):
    from datetime import date
    from birthday_pi import main
    monkeypatch.setattr(main, "today", lambda *a: date(2026, 10, 14))
    client = set_up
    client.post("/people/new", data={"name": "Soon", "birth_month": "12", "birth_day": "13"})  # 60 days
    client.post("/people/new", data={"name": "Later", "birth_month": "12", "birth_day": "14"})  # 61 days
    for text in (client.get("/").text, client.get("/screen/content").text):
        assert "Soon" in text and "Later" not in text


def test_old_couple_anniversaries_are_migrated(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    old = sqlite3.connect(tmp_path / "birthday-pi.db")
    old.executescript("""
        CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_owner INTEGER NOT NULL DEFAULT 0,
            birth_month INTEGER, birth_day INTEGER, birth_year INTEGER, created_at TEXT);
        CREATE TABLE anniversaries (id INTEGER PRIMARY KEY, person_a INTEGER NOT NULL, person_b INTEGER NOT NULL,
            month INTEGER NOT NULL, day INTEGER NOT NULL, year INTEGER, UNIQUE (person_a, person_b));
        INSERT INTO people (id, name) VALUES (1, 'Sam'), (2, 'Dana');
        INSERT INTO anniversaries (person_a, person_b, month, day, year) VALUES (1, 2, 9, 9, 2013);
    """)
    old.commit()
    old.close()
    row = db.connect().execute("SELECT person_id, kind, month, day, year FROM anniversaries").fetchone()
    assert tuple(row) == (1, "wedding", 9, 9, 2013)


def test_person_form_rejects_bad_dates(set_up):
    client = set_up
    r = client.post("/people/new", data={"name": "Leo", "birth_month": "2", "birth_day": "30"})
    assert r.status_code == 400 and "February doesn&#39;t have a day 30" in r.text
    r = client.post("/people/new", data={"name": "Leo", "birth_month": "2"})
    assert r.status_code == 400 and "both the month and the day" in r.text
    r = client.post("/people/new", data={"name": "", "ann_count": "1", "ann_0_kind": "wedding", "ann_0_month": "4", "ann_0_day": "31"})
    assert "Please type a name" in r.text and "April doesn&#39;t have a day 31" in r.text


def test_remove_person_but_never_grandma(set_up):
    client = set_up
    client.post("/people/new", data={"name": "Ben"})
    conn = db.connect()
    ben = conn.execute("SELECT id FROM people WHERE name = 'Ben'").fetchone()[0]
    client.post(f"/people/{ben}/remove")
    assert conn.execute("SELECT COUNT(*) FROM people WHERE name = 'Ben'").fetchone()[0] == 0
    owner = db.owner(conn)["id"]
    client.post(f"/people/{owner}/remove")
    assert db.owner(conn) is not None


def test_monitor_home_lists_coming_up(set_up):
    client = set_up
    soon = date.today() + timedelta(days=30)  # past the reminder window
    client.post("/people/new", data={"name": "Mia", "birth_month": str(soon.month), "birth_day": str(soon.day)})
    screen = client.get("/screen/content").text
    assert "Coming up" in screen and "Mia" in screen
    assert "Let's meet your family." not in screen


def test_reset_pin_untrusts_grandmas_devices(set_up, capsys):
    client = set_up
    assert client.get("/", follow_redirects=False).status_code == 200
    assert cli.main(["reset-pin", "--pin", "9999"]) == 0
    assert client.get("/", follow_redirects=False).headers["location"] == "/who"
    r = client.post("/pin", data={"pin": "9999"}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_load_sample_only_on_fresh_pi(client, capsys):
    assert cli.main(["load-sample"]) == 0
    assert "PIN is 1234" in capsys.readouterr().out
    assert cli.main(["load-sample"]) == 1
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 9
    assert conn.execute("SELECT COUNT(*) FROM anniversaries").fetchone()[0] == 2
    assert "Aunt Rosa" in client.get("/screen/content").text


def test_anniversary_can_be_in_the_future(set_up, monkeypatch):
    from birthday_pi import main
    monkeypatch.setattr(main, "today", lambda *a: date(2026, 10, 14))
    client = set_up
    r = client.post("/people/new", data={"name": "Leo", "ann_count": "1", "ann_0_kind": "graduation",
                                         "ann_0_month": "6", "ann_0_day": "1", "ann_0_year": "2028"},
                    follow_redirects=False)
    assert r.status_code == 303
    r = client.post("/people/new", data={"name": "Mia", "birth_month": "1", "birth_day": "1", "birth_year": "2028"})
    assert r.status_code == 400 and "between 1900 and 2026" in r.text  # birthdays stay in the past


def test_future_anniversary_first_shows_on_the_day(tmp_path, monkeypatch):
    from birthday_pi.dates import upcoming
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    conn = db.connect()
    pid = conn.execute("INSERT INTO people (name) VALUES ('Leo')").lastrowid
    conn.execute("INSERT INTO anniversaries (person_id, kind, month, day, year) VALUES (?, 'graduation', 6, 1, 2028)", (pid,))
    assert upcoming(conn, date(2027, 5, 20))[0].when == date(2028, 6, 1)  # not June 2027
    c = upcoming(conn, date(2028, 5, 20))[0]
    assert c.when == date(2028, 6, 1) and c.detail == "Graduation day"
    assert upcoming(conn, date(2029, 5, 20))[0].detail == "Graduation anniversary · 1 year"


def test_got_it_on_monitor_clears_phone_too(set_up):
    client = set_up
    soon = date.today() + timedelta(days=3)
    client.post("/people/new", data={"name": "Leo", "birth_month": str(soon.month), "birth_day": str(soon.day)})
    screen = client.get("/screen/content").text
    assert "Leo&#39;s birthday is in 3 days" in screen and 'data-reminders="p' in screen
    assert "Leo&#39;s birthday is in 3 days" in client.get("/").text
    key = screen.split('name="key" value="')[1].split('"')[0]
    r = client.post("/reminders/ack", data={"key": key, "back": "/screen"}, follow_redirects=False)
    assert r.headers["location"] == "/screen"
    assert "Got it" not in client.get("/").text
    assert "Got it" not in client.get("/screen/content").text


def test_pretend_date_needs_grandma_and_shows_banner(client):
    client.post("/setup", data={"owner_name": "Grandma", "pin": "2468", "pin2": "2468"})
    client.post("/who", data={"new_name": "Dana"})
    assert client.get("/settings/date", follow_redirects=False).headers["location"] == "/pin"
    client.post("/pin", data={"pin": "2468"})
    later = date.today() + timedelta(days=200)
    client.post("/settings/date", data={"date": later.isoformat(), "idle": "300", "action": "save"})
    assert "Testing: pretending today is" in client.get("/").text
    assert "testing" in client.get("/screen/content").text
    client.post("/settings/date", data={"action": "normal"})
    assert "Testing: pretending" not in client.get("/").text


def test_screen_reports_its_build_so_it_can_reload(client):
    build = client.get("/screen/content").headers["X-Screen-Build"]
    assert f'data-build="{build}"' in client.get("/screen").text


def test_testing_wait_before_photos(set_up):
    client = set_up
    assert client.get("/screen/content").headers["X-Screen-Idle"] == "300"
    client.post("/settings/date", data={"date": date.today().isoformat(), "idle": "10", "action": "save"})
    assert client.get("/screen/content").headers["X-Screen-Idle"] == "10"
    assert 'data-idle="10"' in client.get("/screen").text
    assert "photos after 10 seconds" in client.get("/").text
    assert "pretending" not in client.get("/").text  # real date kept
    client.post("/settings/date", data={"action": "normal"})
    assert client.get("/screen/content").headers["X-Screen-Idle"] == "300"
    assert 'role="status">Testing' not in client.get("/").text  # banner gone
