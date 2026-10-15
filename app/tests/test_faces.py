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


def test_faces_page_shows_groups_from_approved_photos_only(set_up):
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
    assert "Looked at 4 of 4 photos · 5 faces · 2 groups" in page  # the pending photo's face isn't offered
    assert page.index("in 3 photos · will be asked about") < page.index("in 1 photo<")
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
