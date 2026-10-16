from datetime import date

import pytest

from birthday_pi import db, naming, photos

np = pytest.importorskip("numpy")  # the faces worker's own dependency
from birthday_pi import faces  # noqa: E402
from tests.test_faces import FakeFinder, _photo, _unit  # noqa: E402

MIA, LEO = _unit(1, 0.1), _unit(0.1, 1)


def _family_photos(conn, n_mia=4, n_leo=3, together=True):
    """Mia in n_mia photos and Leo in n_leo (the same photos when together), all approved and scanned."""
    found = {}
    leo_from = 0 if together else n_mia
    for i in range(max(n_mia, leo_from + n_leo)):
        pid = f"{i:016x}"
        _photo(conn, pid)
        found[pid] = ([MIA] if i < n_mia else []) + ([LEO] if leo_from <= i < leo_from + n_leo else [])
    faces.scan_waiting(conn, FakeFinder(found))
    return found


def _group_of(conn, feature_index):
    """The group holding faces like MIA (0) or LEO (1)."""
    for (gid,) in conn.execute("SELECT id FROM face_groups ORDER BY id"):
        emb = faces.from_blob(conn.execute("SELECT embedding FROM faces WHERE group_id = ? LIMIT 1", (gid,)).fetchone()[0])
        if int(np.argmax(emb[:2])) == feature_index:
            return gid


def test_naming_flow_new_person_then_birthday(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    mia = _group_of(conn, 0)
    home = client.get("/").text
    assert "2 people to name in your photos" in home
    listing = client.get("/faces").text
    assert listing.index(f'href="/faces/{mia}"') < listing.index("In 3 photos")  # biggest first
    group_page = client.get(f"/faces/{mia}").text
    assert group_page.count('name="out"') == 4 and "Person 1 of 2" in group_page
    r = client.post(f"/faces/{mia}", data={"action": "who"}, follow_redirects=False)
    assert r.headers["location"] == f"/faces/{mia}/who"
    r = client.post(f"/faces/{mia}/who", data={"new_name": "Mia"}, follow_redirects=False)
    assert r.headers["location"] == f"/faces/{mia}/named"
    named = client.get(r.headers["location"]).text
    assert "That's Mia" in named
    assert "Mia is in <b>4 photos</b>" in named and "Add Mia's birthday" in named and "1 left to name" in named
    assert "1 of 2 named" in client.get("/faces").text


def test_second_group_named_the_same_person_joins_them(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn, together=False)  # e.g. Mia as a baby and Mia now: one person in two groups
    mia, leo = _group_of(conn, 0), _group_of(conn, 1)
    client.post(f"/faces/{mia}/who", data={"new_name": "Mia"})
    client.post(f"/faces/{leo}/who", data={"new_name": "mia"})  # typed again: the same person, not a new one
    assert conn.execute("SELECT COUNT(*) FROM people WHERE name LIKE 'mia'").fetchone()[0] == 1
    named = client.get(f"/faces/{leo}/named").text
    assert "Mia is now in <b>7 photos</b>. 3 more joined the 4 already named Mia." in named
    # Undo takes the second group back off Mia.
    client.post(f"/faces/{leo}/undo")
    assert naming.group(conn, leo)["person_id"] is None and naming.group(conn, mia)["name"] == "Mia"


def test_picking_someone_already_in_birthday_pi(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    rosa = conn.execute("INSERT INTO people (name, birth_month, birth_day) VALUES ('Aunt Rosa', 11, 21)").lastrowid
    leo = _group_of(conn, 1)
    who = client.get(f"/faces/{leo}/who").text
    assert "Aunt Rosa" in who and "Birthday Nov 21 · no photos yet" in who
    client.post(f"/faces/{leo}/who", data={"person_id": str(rosa)})
    named = client.get(f"/faces/{leo}/named").text
    assert "November 21" in named and "3 photos show" in named


def test_not_family_is_never_asked_again(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    mia, leo = _group_of(conn, 0), _group_of(conn, 1)
    r = client.post(f"/faces/{mia}", data={"action": "not_family"}, follow_redirects=False)
    assert r.headers["location"] == f"/faces/{leo}"  # straight on to the next person
    assert [g["id"] for g in naming.to_name(conn)] == [leo]


def test_taken_out_faces_find_another_group(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    mia = _group_of(conn, 0)
    stray = conn.execute("SELECT id FROM faces WHERE group_id = ? ORDER BY id LIMIT 1", (mia,)).fetchone()[0]
    client.post(f"/faces/{mia}", data={"out": str(stray), "action": "who"})
    assert conn.execute("SELECT group_id, not_group FROM faces WHERE id = ?", (stray,)).fetchone()[:] == (None, mia)
    faces.scan_waiting(conn, FakeFinder({}))  # the worker places it on its next round
    placed = conn.execute("SELECT group_id FROM faces WHERE id = ?", (stray,)).fetchone()[0]
    leo = _group_of(conn, 1)
    assert placed not in (None, mia, leo)  # not back with Mia, and not Leo, who's already in that photo
    assert "In 3 photos" in client.get(f"/faces/{mia}/who").text


def test_named_faces_put_photos_in_the_birthday_slideshow(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    client.post(f"/faces/{_group_of(conn, 1)}/who", data={"new_name": "Leo"})
    conn.execute("UPDATE people SET birth_month = 8, birth_day = 30 WHERE name = 'Leo'")
    shown = photos.slideshow(conn, date(2026, 8, 30))
    assert shown["title"] == "Happy birthday, Leo!" and len(shown["photos"]) == 3
    assert "Found by face:</span> Leo" in client.get(f"/photos/{'0' * 16}").text


def test_naming_is_grandma_only(set_up):
    client, conn = set_up, db.connect()
    _family_photos(conn)
    mia = _group_of(conn, 0)
    client.cookies.clear()
    client.post("/who", data={"new_name": "Dana"})
    assert "to name in your photos" not in client.get("/").text
    for url in ("/faces", f"/faces/{mia}", f"/faces/{mia}/who", f"/faces/{mia}/named"):
        assert client.get(url, follow_redirects=False).headers["location"] == "/pin"
    assert client.post(f"/faces/{mia}/who", data={"new_name": "Mallory"}, follow_redirects=False).headers["location"] == "/pin"
    assert naming.group(conn, mia)["person_id"] is None


def test_m5_database_gets_the_new_columns(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    old = sqlite3.connect(tmp_path / "birthday-pi.db")
    old.executescript("""
        CREATE TABLE face_groups (id INTEGER PRIMARY KEY, person_id INTEGER);
        CREATE TABLE faces (id INTEGER PRIMARY KEY, photo_id TEXT NOT NULL, group_id INTEGER, x INTEGER NOT NULL,
            y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL, score REAL NOT NULL, embedding BLOB NOT NULL);
    """)
    old.close()
    conn = db.connect()
    assert "ignored" in [r[1] for r in conn.execute("PRAGMA table_info(face_groups)")]
    assert "not_group" in [r[1] for r in conn.execute("PRAGMA table_info(faces)")]


# ---------- M7: recognising later imports, corrections, forgetting ----------

def _named(client, conn, **kw):
    """Mia (4 photos) and Leo (3) named by Grandma, as in M6."""
    _family_photos(conn, **kw)
    mia, leo = _group_of(conn, 0), _group_of(conn, 1)
    client.post(f"/faces/{mia}/who", data={"new_name": "Mia"})
    client.post(f"/faces/{leo}/who", data={"new_name": "Leo"})
    return mia, leo


def _import(conn, pid, *found):
    _photo(conn, pid)
    faces.scan_waiting(conn, FakeFinder({pid: list(found)}))
    return conn.execute("SELECT id, group_id, ask_group, confirmed FROM faces WHERE photo_id = ?", (pid,)).fetchall()


def test_clear_match_is_named_without_asking(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    assert conn.execute("SELECT COUNT(*) FROM faces WHERE confirmed = 1").fetchone()[0] == 7
    (face,) = _import(conn, "a" * 16, _unit(1, 0.12))
    assert (face["group_id"], face["ask_group"], face["confirmed"]) == (mia, None, 0)
    assert naming.asking(conn) == []


def test_unsure_match_asks_is_this_leo(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    (face,) = _import(conn, "a" * 16, _unit(0.1, 1, 2))  # like Leo, but not clearly (similarity 0.45)
    assert (face["group_id"], face["ask_group"]) == (None, leo)
    assert [(a["id"], a["name"]) for a in naming.asking(conn)] == [(face["id"], "Leo")]
    faces.scan_waiting(conn, FakeFinder({}))  # the worker leaves it for Grandma
    assert naming.ask(conn, face["id"])["ask_group"] == leo
    naming.answer(conn, face["id"], yes=True)
    row = conn.execute("SELECT group_id, ask_group, confirmed FROM faces WHERE id = ?", (face["id"],)).fetchone()
    assert tuple(row) == (leo, None, 1) and naming.asking(conn) == []


def test_no_to_is_this_leo_is_never_asked_again(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    (face,) = _import(conn, "a" * 16, _unit(0.1, 1, 2))
    naming.answer(conn, face["id"], yes=False)
    faces.scan_waiting(conn, FakeFinder({}))
    row = conn.execute("SELECT group_id, ask_group FROM faces WHERE id = ?", (face["id"],)).fetchone()
    assert row["group_id"] not in (None, mia, leo) and row["ask_group"] is None


def test_too_few_confirmed_faces_asks_first(set_up):
    client, conn = set_up, db.connect()
    _named(client, conn, n_leo=2)  # Grandma has only seen Leo twice
    leo = _group_of(conn, 1)
    (face,) = _import(conn, "a" * 16, _unit(0.1, 1))  # an exact match still asks
    assert (face["group_id"], face["ask_group"]) == (None, leo)


def test_look_alikes_ask_rather_than_guess(set_up):
    client, conn = set_up, db.connect()
    _named(client, conn)
    (face,) = _import(conn, "a" * 16, _unit(1, 1))  # just as like Mia as Leo
    assert face["group_id"] is None and face["ask_group"] is not None


def test_two_faces_in_one_photo_are_not_both_the_same_person(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    found = _import(conn, "a" * 16, _unit(1, 0.12), _unit(1, 0.1))  # Mia and a look-alike sibling
    assert sorted(f["group_id"] == mia or f["ask_group"] == mia for f in found) == [False, True]


def test_unnaming_sends_waiting_questions_back(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    (face,) = _import(conn, "a" * 16, _unit(0.1, 1, 2))
    client.post(f"/faces/{leo}/undo")
    assert conn.execute("SELECT COUNT(*) FROM faces WHERE group_id = ? AND confirmed = 1", (leo,)).fetchone()[0] == 0
    assert naming.asking(conn) == []


def test_not_leo_takes_faces_out_and_confirms_the_rest(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    (auto,) = _import(conn, "a" * 16, _unit(0.12, 1))  # named automatically, not yet seen by Grandma
    person = naming.group(conn, leo)["person_id"]
    wrong = naming.person_faces(conn, person)[0]["id"]
    assert naming.not_person(conn, person, [wrong]) == 1
    assert wrong not in [f["id"] for f in naming.person_faces(conn, person)]
    assert conn.execute("SELECT confirmed FROM faces WHERE id = ?", (auto["id"],)).fetchone()[0] == 1


def test_remove_person_forgets_their_face(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    (waiting,) = _import(conn, "a" * 16, _unit(0.1, 1, 2))
    leo_faces = [r[0] for r in conn.execute("SELECT id FROM faces WHERE group_id = ?", (leo,))] + [waiting["id"]]
    for fid in leo_faces:
        assert photos.face_crop_path(fid).exists()
    person = naming.group(conn, leo)["person_id"]
    assert "their face in your photos" in client.get(f"/people/{person}/remove").text
    client.post(f"/people/{person}/remove")
    marks = ",".join("?" * len(leo_faces))
    assert conn.execute(f"SELECT COUNT(*) FROM faces WHERE id IN ({marks})", leo_faces).fetchone()[0] == 0
    assert not any(photos.face_crop_path(f).exists() for f in leo_faces)
    assert naming.group(conn, leo) is None and naming.asking(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 5  # the photos stay
    faces.scan_waiting(conn, FakeFinder({}))
    assert [g["id"] for g in naming.to_name(conn)] == []  # nothing about Leo comes back to name
    assert naming.group(conn, mia)["person_id"] is not None


def test_m6_database_counts_named_faces_as_confirmed(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    old = sqlite3.connect(tmp_path / "birthday-pi.db")
    old.executescript("""
        CREATE TABLE face_groups (id INTEGER PRIMARY KEY, person_id INTEGER, ignored TEXT);
        CREATE TABLE faces (id INTEGER PRIMARY KEY, photo_id TEXT NOT NULL, group_id INTEGER, not_group INTEGER,
            x INTEGER NOT NULL, y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL, score REAL NOT NULL,
            embedding BLOB NOT NULL);
        INSERT INTO face_groups VALUES (1, 7, NULL), (2, NULL, NULL);
        INSERT INTO faces VALUES (1, 'p', 1, NULL, 0, 0, 1, 1, 0.9, x''), (2, 'p', 2, NULL, 0, 0, 1, 1, 0.9, x'');
    """)
    old.commit()
    old.close()
    conn = db.connect()
    assert [tuple(r) for r in conn.execute("SELECT id, confirmed, ask_group FROM faces ORDER BY id")] == [(1, 1, None), (2, 0, None)]


def test_is_this_leo_screens(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    first = _import(conn, "a" * 16, _unit(0.1, 1, 2))[0]["id"]
    second = _import(conn, "b" * 16, _unit(1, 0.1, 2))[0]["id"]  # unsure: like Mia
    third = _import(conn, "c" * 16, _unit(0.1, 1, 2.1))[0]["id"]
    conn.execute("UPDATE photos SET width = 1600, height = 1200")
    assert "3 faces to check" in client.get("/").text
    page = client.get("/faces/ask").text
    assert "Is this Leo?" in page and "3 to check" in page and f"/face-files/{first}.jpg" in page
    assert f'/photo-files/{"a" * 16}-thumb.jpg' in page and 'class="ring" style="left: ' in page
    r = client.post(f"/faces/ask/{first}?yes=0", data={"action": "yes"}, follow_redirects=False)
    assert r.headers["location"] == f"/faces/ask?after={first}&yes=1"
    page = client.get(r.headers["location"]).text
    assert "Is this Mia?" in page and "2 to check" in page
    client.post(f"/faces/ask/{second}?yes=1", data={"action": "no"})
    r = client.post(f"/faces/ask/{third}?yes=1", data={"action": "skip"}, follow_redirects=False)
    done = client.get(r.headers["location"]).text
    assert "All checked" in done and "1 face added" in done and "1 you skipped" in done
    assert [a["id"] for a in naming.asking(conn)] == [third]
    assert conn.execute("SELECT group_id, confirmed FROM faces WHERE id = ?", (first,)).fetchone()[:] == (leo, 1)
    assert "Is this Leo?" in client.get("/faces/ask").text  # asked again next time


def test_is_this_all_leo_screen(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    auto = _import(conn, "a" * 16, _unit(0.12, 1))[0]["id"]
    person = naming.group(conn, leo)["person_id"]
    edit = client.get(f"/people/{person}").text
    assert f'href="/people/{person}/faces"' in edit and "In 4 photos. Is this all Leo?" in edit
    page = client.get(f"/people/{person}/faces").text
    assert page.count('name="out"') == 4 and page.count('class="new-badge on-tile"') == 1 and "Named by Birthday Pi" in page
    wrong = next(f["id"] for f in naming.person_faces(conn, person) if f["id"] != auto)
    r = client.post(f"/people/{person}/faces", data={"out": str(wrong)}, follow_redirects=False)
    assert r.headers["location"] == f"/people/{person}"
    assert wrong not in [f["id"] for f in naming.person_faces(conn, person)]
    assert conn.execute("SELECT confirmed FROM faces WHERE id = ?", (auto,)).fetchone()[0] == 1
    assert "Named by Birthday Pi" not in client.get(f"/people/{person}/faces").text


def test_checking_faces_is_grandma_only(set_up):
    client, conn = set_up, db.connect()
    mia, leo = _named(client, conn)
    face = _import(conn, "a" * 16, _unit(0.1, 1, 2))[0]["id"]
    person = naming.group(conn, leo)["person_id"]
    client.cookies.clear()
    client.post("/who", data={"new_name": "Dana"})
    assert "to check" not in client.get("/").text
    assert "Leo's faces" not in client.get(f"/people/{person}").text
    for url in ("/faces/ask", f"/people/{person}/faces"):
        assert client.get(url, follow_redirects=False).headers["location"] == "/pin"
    for url, data in ((f"/faces/ask/{face}", {"action": "yes"}), (f"/people/{person}/faces", {"out": str(face)})):
        assert client.post(url, data=data, follow_redirects=False).headers["location"] == "/pin"
    assert naming.ask(conn, face) is not None
