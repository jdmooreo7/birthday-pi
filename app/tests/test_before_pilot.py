"""Before the pilot: anyone's name (no "Grandma" default), the screen on a phone, special dates and remembering."""
import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from birthday_pi import db
from birthday_pi.dates import remembering_today, upcoming
from birthday_pi.photos import slideshow
from birthday_pi.reminders import active
from test_photos import as_visitor, jpeg, upload


def nana(client):
    """Set up for "Nana", with this client trusted as her."""
    client.post("/setup", data={"owner_name": "Nana", "pin": "2468", "pin2": "2468"})
    client.post("/pin", data={"pin": "2468"})
    return client


def pretend(monkeypatch, day: date):
    """A pretend date, which only counts while testing is switched on."""
    monkeypatch.setenv("BIRTHDAY_PI_TESTING", "1")
    db.set_setting(db.connect(), "pretend_date", day.isoformat())


def add(client, **form):
    form.setdefault("ann_count", "1")
    return client.post("/people/new", data=form, follow_redirects=False)


def person_id(name: str) -> int:
    return db.connect().execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()[0]


# ---------- Anyone's name ----------

def test_setup_asks_who_it_is_for_with_no_default_name(client):
    page = client.get("/setup").text
    assert "Who is this for?" in page and 'name="owner_name" value=""' in page
    assert "like Grandma, Nana, Dad or Maria" in page  # only as a hint
    for word in (" her ", " she ", "Her PIN"):
        assert word not in page
    r = client.post("/setup", data={"owner_name": "", "pin": "2468", "pin2": "2468"})
    assert r.status_code == 400 and "Please type the name the family uses." in r.text


def test_every_page_uses_the_name_given_at_setup(client):
    nana(client)
    upload(client, jpeg("blue"))
    as_visitor(client, "Dana")
    upload(client, jpeg("green"))
    pages = {path: client.get(path).text for path in ("/", "/photos", "/photos/add", "/people", "/help")}
    assert "waiting for Nana&#39;s OK" in pages["/"]
    assert "Your photos waiting for Nana" in pages["/photos"]
    assert "after Nana says OK" in pages["/photos/add"]
    photo = db.connect().execute("SELECT id FROM photos WHERE status = 'pending'").fetchone()["id"]
    pages["photo"] = client.get(f"/photos/{photo}").text
    assert "waiting for Nana&#39;s OK" in pages["photo"]
    pages["screen"] = client.get("/screen").text
    assert "for Nana&#39;s OK" in pages["screen"]
    pages["screen pin"] = client.get("/screen/approve").text
    assert "<title>Nana&#39;s PIN</title>" in pages["screen pin"]
    for name, text in pages.items():
        assert "Grandma" not in text, name


def test_possessive_of_a_name_ending_in_s(client):
    client.post("/setup", data={"owner_name": "Doris", "pin": "2468", "pin2": "2468"})
    client.post("/pin", data={"pin": "2468"})
    as_visitor(client, "Dana")
    upload(client, jpeg("green"))
    assert "waiting for Doris&#39; OK" in client.get("/").text


# ---------- The screen on a phone ----------

def test_screen_has_its_own_icon_and_bookmark_name(set_up):
    screen = set_up.get("/screen").text
    assert '<link rel="apple-touch-icon"' in screen
    assert '<meta name="apple-mobile-web-app-title" content="Birthday Pi screen">' in screen
    assert '<title>Birthday Pi screen</title>' in screen
    assert 'class="phone-home" href="/"' in screen  # shown only on a phone held upright
    assert 'class="phone-photo"' in screen and 'class="phone-url"' in screen


def test_see_the_screen_is_on_her_home_only(set_up):
    assert 'href="/screen"' in set_up.get("/").text
    as_visitor(set_up, "Dana")
    assert 'href="/screen"' not in set_up.get("/").text


# ---------- Special dates ----------

def test_special_dates_form_and_something_else(set_up):
    form = set_up.get("/people/new").text
    assert "Special dates" in form and "Anniversar" not in form
    for option in ("Wedding anniversary", "Graduation", "Remembering them", "Something else"):
        assert f">{option}</option>" in form
    r = add(set_up, name="Dana", ann_0_kind="other", ann_0_month="8", ann_0_day="3", ann_0_year="2020")
    assert r.status_code == 400 and "Please type what you call it." in r.text
    r = add(set_up, name="Dana", ann_0_kind="other", ann_0_label="First day in the new house",
            ann_0_month="8", ann_0_day="3", ann_0_year="2020")
    assert r.status_code == 303
    assert "First day in the new house · August 3" in set_up.get("/people").text
    assert 'value="First day in the new house"' in set_up.get(f"/people/{person_id('Dana')}").text
    c = upcoming(db.connect(), date(2026, 7, 31))[0]
    assert c.detail == "First day in the new house · 6 years" and not c.quiet
    r = active(db.connect(), date(2026, 7, 31))[0]
    assert r.headline == "Dana's First day in the new house is in 3 days"
    # A label typed for another kind isn't kept.
    add(set_up, name="Leo", ann_0_kind="wedding", ann_0_label="ignored", ann_0_month="6", ann_0_day="12")
    assert db.connect().execute("SELECT label FROM anniversaries WHERE kind = 'wedding'").fetchone()[0] is None


def test_old_databases_get_the_new_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    old = sqlite3.connect(tmp_path / "birthday-pi.db")
    old.executescript("""
        CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_owner INTEGER NOT NULL DEFAULT 0,
            birth_month INTEGER, birth_day INTEGER, birth_year INTEGER, created_at TEXT);
        CREATE TABLE anniversaries (id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL, kind TEXT NOT NULL,
            month INTEGER NOT NULL, day INTEGER NOT NULL, year INTEGER);
        INSERT INTO people (name, birth_month, birth_day) VALUES ('Dana', 3, 14);
        INSERT INTO anniversaries (person_id, kind, month, day, year) VALUES (1, 'wedding', 6, 12, 2014);
    """)
    old.close()
    conn = db.connect()
    assert conn.execute("SELECT remembered FROM people").fetchone()[0] == 0
    assert conn.execute("SELECT label FROM anniversaries").fetchone()[0] is None
    assert [c.detail for c in upcoming(conn, date(2026, 3, 1))] == ["Birthday", "Wedding anniversary · 12 years"]


# ---------- Remembering ----------

def test_only_she_can_mark_someone_as_remembered(set_up):
    add(set_up, name="Ray", birth_month="3", birth_day="3", birth_year="1956", remembered="1")
    ray = person_id("Ray")
    assert db.connect().execute("SELECT remembered FROM people WHERE id = ?", (ray,)).fetchone()[0] == 1
    assert "We're remembering Ray" in set_up.get(f"/people/{ray}").text
    assert "Remembering Ray" in set_up.get("/people").text
    owner = db.owner(db.connect())["id"]
    assert 'name="remembered"' not in set_up.get(f"/people/{owner}").text  # not for the person it's for
    from birthday_pi.main import app
    visitor = TestClient(app)
    visitor.post("/who", data={"new_name": "Dana"})
    assert 'name="remembered"' not in visitor.get(f"/people/{ray}").text
    visitor.post(f"/people/{ray}", data={"name": "Ray", "birth_month": "3", "birth_day": "3", "ann_count": "1"})
    assert db.connect().execute("SELECT remembered FROM people WHERE id = ?", (ray,)).fetchone()[0] == 1  # kept
    leo = person_id("Dana")
    visitor.post(f"/people/{leo}", data={"name": "Dana", "remembered": "1", "ann_count": "1"})
    assert db.connect().execute("SELECT remembered FROM people WHERE id = ?", (leo,)).fetchone()[0] == 0  # ignored


def test_a_remembered_birthday_is_quiet(set_up, monkeypatch):
    add(set_up, name="Ray", birth_month="3", birth_day="3", birth_year="1956", remembered="1")
    add(set_up, name="Leo", birth_month="3", birth_day="20")
    add(set_up, name="Sam", remembered="1")  # no birthday: never nagged for one
    conn = db.connect()
    # No countdown, no reminders, not in "Coming up"; not someone who uses a phone.
    assert [c.name for c in upcoming(conn, date(2026, 2, 25))] == ["Leo"]
    assert active(conn, date(2026, 2, 25)) == [] and active(conn, date(2026, 3, 3)) == []
    assert "Ray" not in set_up.get("/who").text and "Sam" not in set_up.get("/who").text
    assert "Sam" not in set_up.get("/").text.split("need a birthday")[-1][:200]
    # On the day: quiet everywhere.
    [c] = remembering_today(conn, date(2026, 3, 3))
    assert c.name == "Ray" and c.extra == "would have been 70"
    assert slideshow(conn, date(2026, 3, 3))["title"] == "Remembering Ray"
    pretend(monkeypatch, date(2026, 3, 3))
    home = set_up.get("/").text
    assert "Remembering Ray" in home and "Would have been 70" in home and "Got it" not in home
    screen = set_up.get("/screen/content").text
    assert 'class="remember-card"' in screen and "Remembering Ray" in screen and "Got it" not in screen


def test_birthday_and_remembering_on_the_same_day(set_up, monkeypatch):
    add(set_up, name="Mia", birth_month="3", birth_day="3", birth_year="2019")
    add(set_up, name="Ray", ann_0_kind="remembering", ann_0_month="3", ann_0_day="3", ann_0_year="2021")
    conn = db.connect()
    assert [c.name for c in upcoming(conn, date(2026, 2, 1))] == ["Mia"]  # no countdown to a remembrance
    assert [r.headline for r in active(conn, date(2026, 3, 3))] == ["It's Mia's birthday"]
    assert slideshow(conn, date(2026, 3, 3))["title"] == "Happy birthday, Mia!"
    pretend(monkeypatch, date(2026, 3, 3))
    screen = set_up.get("/screen/content").text
    assert "It&#39;s Mia&#39;s birthday" in screen and "Got it" in screen  # the birthday stays the main card
    strip = screen.split('class="remember-strip"')[1]
    assert "Also today" in strip and "Remembering Ray" in strip and "5 years" in strip
