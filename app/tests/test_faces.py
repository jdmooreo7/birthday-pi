import sqlite3

import pytest

from birthday_pi import db, photos

np = pytest.importorskip("numpy")  # the faces worker's own dependency; the app doesn't need it
from birthday_pi import faces  # noqa: E402


def _unit(*values):
    v = np.zeros(128, dtype=np.float32)
    v[: len(values)] = values
    return v / np.linalg.norm(v)


def _photo(conn, photo_id, status="approved"):
    conn.execute("INSERT INTO photos (id, sha256, status) VALUES (?, ?, ?)", (photo_id, photo_id, status))


class FakeFinder:
    """Stands in for OpenCV: each photo id maps to the embeddings of the faces "found" in it."""

    def __init__(self, found):
        self.found = found
        self.cv2 = self

    def find(self, path):
        return [(np.array([10, 20, 60, 60] + [0] * 10 + [0.95]), b"crop", f) for f in self.found[path.stem]]

    def imwrite(self, path, crop):
        with open(path, "wb") as f:
            f.write(crop)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    return db.connect()


def test_faces_of_the_same_person_are_grouped(conn):
    mia, leo = _unit(1, 0.1), _unit(0.1, 1)
    finder = FakeFinder({"a" * 16: [mia, leo], "b" * 16: [_unit(1, 0.15)], "c" * 16: [_unit(0.12, 1), _unit(1, 0.05)]})
    for pid in finder.found:
        _photo(conn, pid)
    assert faces.scan_waiting(conn, finder) == (3, 5)
    groups = [sorted(r[0] for r in conn.execute("SELECT photo_id FROM faces WHERE group_id = ?", (g,)))
              for (g,) in conn.execute("SELECT id FROM face_groups ORDER BY id")]
    assert groups == [["a" * 16, "b" * 16, "c" * 16], ["a" * 16, "c" * 16]]
    assert conn.execute("SELECT COUNT(*) FROM photos WHERE faces_scanned = 0").fetchone()[0] == 0
    assert faces.scan_waiting(conn, finder) == (0, 0)  # nothing left to do
    face_id = conn.execute("SELECT MIN(id) FROM faces").fetchone()[0]
    assert faces.crop_path(face_id).read_bytes() == b"crop"
    assert db.get_setting(conn, faces.HEARTBEAT)


def test_groups_are_remembered_between_rounds(conn):
    _photo(conn, "a" * 16)
    faces.scan_waiting(conn, FakeFinder({"a" * 16: [_unit(1, 0.1)]}))
    _photo(conn, "b" * 16)
    faces.scan_waiting(conn, FakeFinder({"b" * 16: [_unit(1, 0.12), _unit(0, 0, 1)]}))
    assert conn.execute("SELECT COUNT(*) FROM face_groups").fetchone()[0] == 2


def test_nobody_appears_twice_in_one_photo(conn):
    _photo(conn, "a" * 16)
    faces.scan_waiting(conn, FakeFinder({"a" * 16: [_unit(1, 0.1), _unit(1, 0.12)]}))  # look-alike siblings
    assert conn.execute("SELECT COUNT(DISTINCT group_id) FROM faces").fetchone()[0] == 2


def test_unreadable_photo_is_marked_done(conn):
    _photo(conn, "a" * 16)

    class Broken(FakeFinder):
        def find(self, path):
            return None

    assert faces.scan_waiting(conn, Broken({})) == (1, 0)
    assert conn.execute("SELECT faces_scanned FROM photos").fetchone()[0] == 1


def test_deleting_a_photo_removes_its_faces_and_crops(conn):
    _photo(conn, "a" * 16, status="pending")
    faces.scan_waiting(conn, FakeFinder({"a" * 16: [_unit(1)]}))
    face_id = conn.execute("SELECT id FROM faces").fetchone()[0]
    assert faces.crop_path(face_id).exists()
    photos.delete(conn, "a" * 16)
    assert conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 0
    assert not faces.crop_path(face_id).exists()


def test_v01_photos_table_gets_scanned_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    old = sqlite3.connect(tmp_path / "birthday-pi.db")
    old.executescript("""
        CREATE TABLE photos (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, uploader_id INTEGER, status TEXT NOT NULL,
            hidden INTEGER NOT NULL DEFAULT 0, width INTEGER, height INTEGER, taken_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO photos (id, sha256, status) VALUES ('aaaaaaaaaaaaaaaa', 'x', 'approved');
    """)
    old.close()
    assert db.connect().execute("SELECT faces_scanned FROM photos").fetchone()[0] == 0


def test_faces_page_offers_groups_from_approved_photos_only(set_up):
    client = set_up
    conn = db.connect()
    assert "The face finder isn't running" in client.get("/faces").text
    for pid, status in (("a" * 16, "approved"), ("b" * 16, "approved"), ("c" * 16, "approved"), ("d" * 16, "pending")):
        _photo(conn, pid, status)
    mia = _unit(1, 0.1)
    faces.scan_waiting(conn, FakeFinder({"a" * 16: [mia], "b" * 16: [mia], "c" * 16: [mia, _unit(0, 1)],
                                         "d" * 16: [_unit(0, 0, 1)]}))
    page = client.get("/faces").text
    assert "isn't running" not in page
    assert "found 1 person in 3 or more photos" in page  # the 1-photo group and the pending photo aren't offered
    assert "0 of 1 named" in page and "In 3 photos" in page and "Looked at 4 of 4 photos" in page
    face_id = conn.execute("SELECT MIN(id) FROM faces").fetchone()[0]
    assert client.get(f"/face-files/{face_id}.jpg").content == b"crop"


def test_face_crops_are_only_for_grandmas_devices(client):
    client.post("/setup", data={"owner_name": "Grandma", "pin": "2468", "pin2": "2468"})
    client.cookies.clear()
    assert client.get("/face-files/1.jpg", follow_redirects=False).headers["location"] == "/who"
    client.post("/who", data={"new_name": "Dana"})
    assert client.get("/face-files/1.jpg", follow_redirects=False).headers["location"] == "/pin"


def test_health_check_follows_the_heartbeat(conn):
    assert not faces.healthy()
    db.set_setting(conn, faces.HEARTBEAT, "2020-01-01T00:00:00")
    assert not faces.healthy()
    from datetime import datetime
    db.set_setting(conn, faces.HEARTBEAT, datetime.now().isoformat(timespec="seconds"))
    assert faces.healthy()


# ---------- v0.2.4: tidying the unnamed groups after new photos ----------

def _at(degrees):
    """A face embedding at this angle: 0° and 70° are different people (cosine 0.34), 30° is between."""
    import math
    return _unit(math.cos(math.radians(degrees)), math.sin(math.radians(degrees)))


def _face(conn, photo_id, group_id, feature, confirmed=0, not_group=None):
    if not conn.execute("SELECT 1 FROM photos WHERE id = ?", (photo_id,)).fetchone():
        _photo(conn, photo_id)
        conn.execute("UPDATE photos SET faces_scanned = 1 WHERE id = ?", (photo_id,))
    if not conn.execute("SELECT 1 FROM face_groups WHERE id = ?", (group_id,)).fetchone():
        conn.execute("INSERT INTO face_groups (id) VALUES (?)", (group_id,))
    return conn.execute(
        "INSERT INTO faces (photo_id, group_id, x, y, w, h, score, embedding, confirmed, not_group) "
        "VALUES (?, ?, 0, 0, 60, 60, 0.9, ?, ?, ?)", (photo_id, group_id, faces.to_blob(feature), confirmed, not_group)
    ).lastrowid


def _groups(conn):
    return [sorted(r[0] for r in conn.execute("SELECT photo_id FROM faces WHERE group_id = ?", (g,)))
            for (g,) in conn.execute("SELECT DISTINCT group_id FROM faces WHERE group_id IS NOT NULL ORDER BY group_id")]


def test_a_new_photo_can_show_two_groups_are_one_person(conn):
    finder = FakeFinder({"a" * 16: [_at(0)], "b" * 16: [_at(70)], "c" * 16: [_at(30)]})
    for pid in ("a" * 16, "b" * 16):
        _photo(conn, pid)
    faces.scan_waiting(conn, finder)
    assert len(_groups(conn)) == 2  # too different to be one person, so far
    _photo(conn, "c" * 16)
    faces.scan_waiting(conn, finder)
    assert _groups(conn) == [["a" * 16, "b" * 16, "c" * 16]]  # c joins a, and then a and b look alike
    assert conn.execute("SELECT COUNT(*) FROM face_groups").fetchone()[0] == 1  # the emptied group is gone


def test_groups_with_a_photo_in_common_never_merge(conn):
    _face(conn, "a" * 16, 1, _at(0))
    _face(conn, "a" * 16, 2, _at(20))  # two look-alikes side by side in one photo
    assert faces.tidy(conn) == (0, 0, 0) and len(_groups(conn)) == 2


def test_a_face_she_took_out_never_goes_back(conn):
    _face(conn, "a" * 16, 1, _at(0))
    _face(conn, "b" * 16, 2, _at(10), not_group=1)  # she said this one isn't group 1's person
    assert faces.tidy(conn) == (0, 0, 0) and len(_groups(conn)) == 2


def test_named_and_set_aside_groups_are_never_merged(conn):
    conn.execute("INSERT INTO people (id, name) VALUES (7, 'Mia')")
    conn.execute("INSERT INTO face_groups (id, person_id) VALUES (1, 7)")
    conn.execute("INSERT INTO face_groups (id, ignored) VALUES (2, 'not_family')")
    _face(conn, "a" * 16, 1, _at(0))  # Mia
    _face(conn, "b" * 16, 2, _at(80))
    _face(conn, "c" * 16, 3, _at(82))  # like the set-aside group, and like each other
    _face(conn, "d" * 16, 4, _at(78))
    assert faces.tidy(conn) == (0, 0, 1)
    assert _groups(conn) == [["a" * 16], ["b" * 16], ["c" * 16, "d" * 16]]


def test_old_faces_are_named_or_asked_about_once_someone_is_named(conn):
    conn.execute("INSERT INTO people (id, name) VALUES (7, 'Mia')")
    conn.execute("INSERT INTO face_groups (id, person_id) VALUES (1, 7)")
    for i in range(3):
        _face(conn, f"{i:016x}", 1, _at(i), confirmed=1)
    clear = _face(conn, "a" * 16, 2, _at(5))  # clearly Mia
    unsure = _face(conn, "b" * 16, 3, _at(64))  # cosine 0.46: maybe Mia
    corrected = _face(conn, "c" * 16, 4, _at(5), not_group=9)  # she has corrected this face before: left alone
    twice = _face(conn, f"{0:016x}", 5, _at(6))  # Mia is already in this photo
    stranger = _face(conn, "d" * 16, 6, _at(90))
    assert faces.tidy(conn) == (1, 1, 1)
    rows = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, group_id, ask_group FROM faces")}
    assert rows[clear] == (1, None) and rows[unsure] == (None, 1) and rows[stranger] == (6, None)
    assert rows[corrected] == rows[twice] == (4, None)  # not Mia, but alike: they merge, still unnamed
    assert faces.tidy(conn) == (0, 0, 0)  # nothing more to do the second time


def test_the_worker_tidies_once_when_it_starts(conn):
    _face(conn, "a" * 16, 1, _at(0))
    _face(conn, "b" * 16, 2, _at(10))
    assert faces.scan_waiting(conn, FakeFinder({})) == (0, 0) and len(_groups(conn)) == 2  # nothing new: no tidy
    faces.scan_waiting(conn, FakeFinder({}), tidy_anyway=True)
    assert len(_groups(conn)) == 1
