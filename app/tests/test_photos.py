import io
from datetime import date

from PIL import Image

from birthday_pi import cli, db, photos


def jpeg(colour="red", size=(3000, 2000), exif=False) -> bytes:
    img = Image.new("RGB", size, colour)
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = "TestCam"  # camera make
        kwargs["exif"] = e.tobytes()
    img.save(buf, "JPEG", **kwargs)
    return buf.getvalue()


def upload(client, *files):
    return client.post("/photos/add", files=[("photos", (f"p{i}.jpg", data, "image/jpeg")) for i, data in enumerate(files)])


def as_visitor(client, name="Dana"):
    client.cookies.clear()
    client.post("/who", data={"new_name": name})


def test_grandma_uploads_go_straight_on_screen_and_are_resized(set_up):
    client = set_up
    r = upload(client, jpeg(exif=True))
    assert "1 photo added" in r.text and "on the screen now" in r.text
    conn = db.connect()
    ph = conn.execute("SELECT * FROM photos").fetchone()
    assert ph["status"] == "approved" and (ph["width"], ph["height"]) == (1620, 1080)
    saved = Image.open(photos.file_path(ph["id"]))
    assert not saved.getexif()  # camera and location details removed
    assert client.get(f"/photo-files/{ph['id']}-thumb.jpg").status_code == 200


def test_visitor_upload_waits_for_grandma_then_approve(set_up):
    client = set_up
    as_visitor(client)
    r = upload(client, jpeg("blue"), jpeg("green"))
    assert "2 photos added" in r.text and "after Grandma says OK" in r.text
    assert "2 of your photos are waiting" in client.get("/").text
    assert client.get("/photos/review", follow_redirects=False).headers["location"] == "/pin"
    conn = db.connect()
    first, second = [r["id"] for r in conn.execute("SELECT id FROM photos ORDER BY id")]
    # Visitors can't approve.
    client.post(f"/photos/{first}/decision", data={"action": "approve"})
    assert conn.execute("SELECT COUNT(*) FROM photos WHERE status = 'pending'").fetchone()[0] == 2
    # Grandma's trusted phone can, without the PIN.
    client.cookies.clear()
    owner = db.owner(conn)["id"]
    client.post("/who", data={"person_id": owner})
    client.post("/pin", data={"pin": "2468"})
    assert "2 photos need your OK" in client.get("/").text
    client.post(f"/photos/{first}/decision", data={"action": "approve", "back": "/photos/review"})
    client.post(f"/photos/{second}/decision", data={"action": "reject", "back": "/photos/review"})
    assert conn.execute("SELECT status FROM photos").fetchall()[0][0] == "approved"
    assert conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 1
    assert not photos.file_path(second).exists()


def test_duplicates_and_non_photos(set_up):
    client = set_up
    data = jpeg()
    upload(client, data)
    r = client.post("/photos/add", files=[("photos", ("a.jpg", data, "image/jpeg")),
                                          ("photos", ("notes.txt", b"hello", "text/plain"))])
    assert "1 was already on the Pi" in r.text and "notes.txt isn" in r.text


def test_hide_and_show(set_up):
    client = set_up
    upload(client, jpeg())
    conn = db.connect()
    pid = conn.execute("SELECT id FROM photos").fetchone()[0]
    client.post(f"/photos/{pid}/decision", data={"action": "hide"})
    assert client.get("/screen/photos").json()["photos"] == []
    client.post(f"/photos/{pid}/decision", data={"action": "show"})
    assert client.get("/screen/photos").json()["photos"] == [f"/photo-files/{pid}.jpg"]


def test_slideshow_shows_only_their_photos_on_their_day(set_up, monkeypatch):
    from birthday_pi import main
    monkeypatch.setattr(main, "today", lambda *a: date(2026, 10, 14))
    client = set_up
    client.post("/people/new", data={"name": "Rosa", "birth_month": "10", "birth_day": "14"})
    upload(client, jpeg("red"), jpeg("blue"))
    conn = db.connect()
    rosa = conn.execute("SELECT id FROM people WHERE name = 'Rosa'").fetchone()[0]
    first = conn.execute("SELECT id FROM photos ORDER BY id").fetchone()[0]
    client.post(f"/photos/{first}/tags", data={"person": [str(rosa)]})
    show = client.get("/screen/photos").json()
    assert show == {"photos": [f"/photo-files/{first}.jpg"], "title": "Happy birthday, Rosa!"}


def test_monitor_approval_needs_pin_each_time(set_up):
    client = set_up
    as_visitor(client)
    upload(client, jpeg())
    client.cookies.clear()  # the monitor has no device cookie
    assert "new photo for Grandma" in client.get("/screen/content").text
    assert "enter your PIN" in client.get("/screen/approve").text
    pid = db.connect().execute("SELECT id FROM photos").fetchone()[0]
    client.post("/screen/approve/decide", data={"photo_id": pid, "action": "approve"})
    assert db.connect().execute("SELECT status FROM photos").fetchone()[0] == "pending"  # still locked
    r = client.post("/screen/approve/pin", data={"pin": "0000"})
    assert r.status_code == 400
    client.post("/screen/approve/pin", data={"pin": "2468"})
    assert "Show these on the screen?" in client.get("/screen/approve").text
    client.post("/screen/approve/decide", data={"photo_id": pid, "action": "approve"})
    assert db.connect().execute("SELECT status FROM photos").fetchone()[0] == "approved"
    client.post("/screen/approve/done")
    assert "bp_screen" not in client.cookies


def test_sample_family_has_tagged_photos(client, capsys):
    cli.main(["load-sample"])
    assert "8 drawn photos" in capsys.readouterr().out
    assert len(client.get("/screen/photos").json()["photos"]) >= 1


def test_photo_files_reject_odd_names(client):
    assert client.get("/photo-files/..%2Fbirthday-pi.db").status_code == 404
    assert client.get("/photo-files/abc.jpg").status_code == 404
