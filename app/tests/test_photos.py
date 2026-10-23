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


def scene(seed=1, taken=None, size=(2400, 1600), quality=90) -> bytes:
    """A photo with some detail (so it has a fingerprint), optionally with the date it was taken."""
    from PIL import ImageDraw
    img = Image.new("RGB", (480, 320), "white")
    d = ImageDraw.Draw(img)
    for i in range(12):
        x, y = (seed * 37 + i * 53) % 440, (seed * 91 + i * 29) % 280
        d.ellipse((x, y, x + 40 + i * 3, y + 30 + i * 2), fill=((seed * 60 + i * 20) % 255, (i * 40) % 255, 120))
    img = img.resize(size)
    buf = io.BytesIO()
    kwargs = {}
    if taken:
        e = Image.Exif()
        e.get_ifd(0x8769)[36867] = taken
        kwargs["exif"] = e.tobytes()
    img.save(buf, "JPEG", quality=quality, **kwargs)
    return buf.getvalue()


def test_same_photo_saved_again_is_skipped(set_up):
    client = set_up
    upload(client, scene(1, "2026:08:18 09:34:26"))
    # The phone re-saves it smaller and at another quality when sharing: different bytes, same photo.
    r = upload(client, scene(1, "2026:08:18 09:34:26", size=(1200, 800), quality=70))
    assert "No new photos" in r.text and "1 was already on the Pi" in r.text
    assert db.connect().execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 1


def test_look_alikes_that_are_not_the_same_photo_are_kept(set_up):
    client = set_up
    upload(client, scene(1, "2026:08:18 09:34:26"))
    r = upload(client,
               scene(1, "2026:08:18 09:34:27"),  # a burst shot a second later
               scene(2, "2026:08:18 09:34:26"),  # another picture from the same second
               scene(1, size=(1200, 800), quality=70))  # no date taken: only identical files are skipped
    assert "3 photos added" in r.text


def test_photos_from_before_fingerprints_are_still_caught(set_up):
    client = set_up
    upload(client, scene(1, "2026:08:18 09:34:26"))
    conn = db.connect()
    conn.execute("UPDATE photos SET look = NULL")
    assert "1 was already on the Pi" in upload(client, scene(1, "2026:08:18 09:34:26", quality=60)).text
    assert conn.execute("SELECT look FROM photos").fetchone()[0] is not None


def test_grandma_deletes_a_photo_and_its_faces(set_up):
    client = set_up
    upload(client, jpeg())
    conn = db.connect()
    pid = conn.execute("SELECT id FROM photos").fetchone()[0]
    face = conn.execute("INSERT INTO faces (photo_id, x, y, w, h, score, embedding) VALUES (?, 0, 0, 1, 1, 0.9, x'00')",
                        (pid,)).lastrowid
    photos.face_crop_path(face).parent.mkdir(parents=True, exist_ok=True)
    photos.face_crop_path(face).write_bytes(b"crop")
    assert f'href="/photos/{pid}/delete"' in client.get(f"/photos/{pid}").text
    assert "can't be undone" in client.get(f"/photos/{pid}/delete").text
    r = client.post(f"/photos/{pid}/delete")
    assert "Photo deleted." in r.text
    assert conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 0
    assert not photos.file_path(pid).exists() and not photos.file_path(pid, True).exists()
    assert not photos.face_crop_path(face).exists()


def test_deleting_photos_is_grandma_only(set_up):
    client = set_up
    upload(client, jpeg())
    pid = db.connect().execute("SELECT id FROM photos").fetchone()[0]
    as_visitor(client)
    assert "/delete" not in client.get(f"/photos/{pid}").text
    assert client.get(f"/photos/{pid}/delete", follow_redirects=False).headers["location"] == "/pin"
    assert client.post(f"/photos/{pid}/delete", follow_redirects=False).headers["location"] == "/pin"
    assert photos.get(db.connect(), pid) is not None


def test_nobody_named_yet_one_by_one(set_up):
    """Photos on the screen with nobody named: her phone lists them after "On the screen" and steps through them."""
    client = set_up
    upload(client, jpeg("red"), jpeg("blue"), jpeg("green"))
    client.post("/people/new", data={"name": "Leo", "birth_month": "11", "birth_day": "4"})
    conn = db.connect()
    leo = conn.execute("SELECT id FROM people WHERE name = 'Leo'").fetchone()["id"]
    ids = photos.unnamed_ids(conn)
    assert len(ids) == 3
    page = client.get("/photos").text
    assert page.index("On the screen") < page.index("Nobody named yet") and "Name them one by one" in page

    first = client.get(f"/photos/{ids[0]}?next=unnamed").text
    assert "1 of 3" in first and "Save and next" in first and "No one to name" in first
    assert f'href="/photos/{ids[1]}?next=unnamed">Skip for now' in first
    # Naming someone takes it out of the list and moves on to the next one.
    r = client.post(f"/photos/{ids[0]}/tags", data={"person": leo, "next": "unnamed"}, follow_redirects=False)
    assert r.headers["location"] == f"/photos/{ids[1]}?next=unnamed"
    # "No one to name" does too; a photo with nobody to name stays out of the list.
    r = client.post(f"/photos/{ids[1]}/no-one", follow_redirects=False)
    assert r.headers["location"] == f"/photos/{ids[2]}?next=unnamed"
    r = client.post(f"/photos/{ids[2]}/no-one", follow_redirects=False)
    assert r.headers["location"] == "/photos#unnamed"
    assert photos.unnamed_ids(conn) == []
    assert "Everyone's named" in client.get("/photos").text


def test_nobody_named_yet_is_grandma_only(set_up):
    client = set_up
    upload(client, jpeg("red"))
    photo = photos.unnamed_ids(db.connect())[0]
    as_visitor(client)
    page = client.get("/photos").text
    assert "Nobody named yet" not in page and "Everyone's named" not in page
    assert "Save and next" not in client.get(f"/photos/{photo}?next=unnamed").text
    client.post(f"/photos/{photo}/no-one")
    assert photos.unnamed_ids(db.connect()) == [photo]


def test_on_the_screen_shows_the_newest_then_see_all(set_up):
    client = set_up
    upload(client, *[jpeg((i * 15, 80, 120), size=(300 + i, 200)) for i in range(17)])
    page = client.get("/photos").text
    assert "See all 17" in page
    assert "See all" not in client.get("/photos?all=1").text
