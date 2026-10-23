"""Family photos: upload and resize, Grandma's approval, and what the slideshow shows."""
import hashlib
import io
import re
import secrets
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

from . import PRODUCT
from .db import data_dir
from .dates import upcoming

pillow_heif.register_heif_opener()  # iPhone HEIC photos
Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse absurdly large images instead of running out of memory

SCREEN_BOX = (1920, 1080)  # photos are stored at most this size; originals are not kept
THUMB_BOX = (480, 480)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MIN_FREE_BYTES = 2 * 1024**3  # refuse uploads when the SD card gets this full
MAX_FILES_PER_UPLOAD = 50
ID_PATTERN = re.compile(r"[0-9a-f]{16}")
# A photo taken at the same second as one already on the Pi, whose fingerprint differs in at most this many
# of 64 bits, is the same photo saved again (a phone re-saves photos when sharing them). Burst shots are
# taken a second or more apart, so they're kept.
SAME_LOOK_BITS = 6


class UploadError(Exception):
    """A message that can be shown to the person uploading."""


def photo_dir() -> Path:
    path = data_dir() / "photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(photo_id: str, thumb: bool = False) -> Path:
    return photo_dir() / (f"{photo_id}-thumb.jpg" if thumb else f"{photo_id}.jpg")


def _taken_at(img: Image.Image) -> str | None:
    try:
        raw = img.getexif().get_ifd(0x8769).get(36867)  # DateTimeOriginal
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").isoformat() if raw else None
    except (ValueError, TypeError, AttributeError):
        return None


def look(img: Image.Image) -> int:
    """A difference hash: 64 bits saying whether each pixel of a tiny grey copy is brighter than the next.
    The same photo re-saved at another size or quality gives nearly the same bits. Signed, to fit SQLite."""
    px = list(img.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes())
    bits = sum(1 << i for i, (a, b) in enumerate((px[r * 9 + c], px[r * 9 + c + 1]) for r in range(8) for c in range(8)) if a > b)
    return bits - (1 << 64) if bits >= 1 << 63 else bits


def _same_photo(conn: sqlite3.Connection, img: Image.Image, taken: str | None) -> bool:
    """Already on the Pi, saved again? Only photos with the same date taken are compared."""
    if not taken:
        return False
    mine = look(img)
    for row in conn.execute("SELECT id, look FROM photos WHERE taken_at = ?", (taken,)).fetchall():
        theirs = row["look"]
        if theirs is None:  # stored before fingerprints existed
            try:
                with Image.open(file_path(row["id"])) as old:
                    theirs = look(old)
            except OSError:
                continue
            conn.execute("UPDATE photos SET look = ? WHERE id = ?", (theirs, row["id"]))
        if bin((mine ^ theirs) & (2**64 - 1)).count("1") <= SAME_LOOK_BITS:
            return True
    return False


def save_upload(conn: sqlite3.Connection, data: bytes, uploader_id: int, approved: bool) -> str | None:
    """Store one uploaded photo. Returns its id, or None if it was already on the Pi."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("is bigger than 25 MB")
    if shutil.disk_usage(data_dir()).free < MIN_FREE_BYTES:
        raise UploadError("couldn't be added because the Pi is nearly full")
    digest = hashlib.sha256(data).hexdigest()
    if conn.execute("SELECT 1 FROM photos WHERE sha256 = ?", (digest,)).fetchone():
        return None
    try:
        img = Image.open(io.BytesIO(data))
        taken = _taken_at(img)
        # JPEGs decode straight at a reduced scale (still at least screen size): far less memory on the Pi.
        img.draft("RGB", SCREEN_BOX)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise UploadError(f"isn't a photo {PRODUCT} can read")
    img.thumbnail(SCREEN_BOX)
    if _same_photo(conn, img, taken):
        return None
    photo_id = secrets.token_hex(8)
    # Saved without EXIF, so no location or camera details stay on the Pi.
    img.save(file_path(photo_id), "JPEG", quality=85, optimize=True)
    thumb = img.copy()
    thumb.thumbnail(THUMB_BOX)
    thumb.save(file_path(photo_id, thumb=True), "JPEG", quality=80)
    conn.execute(
        "INSERT INTO photos (id, sha256, uploader_id, status, width, height, taken_at, look) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (photo_id, digest, uploader_id, "approved" if approved else "pending", img.width, img.height, taken, look(img)),
    )
    return photo_id


def face_crop_path(face_id: int) -> Path:
    return data_dir() / "faces" / f"{face_id}.jpg"


def delete(conn: sqlite3.Connection, photo_id: str) -> None:
    """Removes the photo, its files, and any faces found in it."""
    face_ids = [r[0] for r in conn.execute("SELECT id FROM faces WHERE photo_id = ?", (photo_id,))]
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    for thumb in (False, True):
        file_path(photo_id, thumb).unlink(missing_ok=True)
    for face_id in face_ids:
        face_crop_path(face_id).unlink(missing_ok=True)


def get(conn: sqlite3.Connection, photo_id: str) -> sqlite3.Row | None:
    if not ID_PATTERN.fullmatch(photo_id or ""):
        return None
    return conn.execute(
        "SELECT ph.*, p.name AS uploader FROM photos ph LEFT JOIN people p ON p.id = ph.uploader_id WHERE ph.id = ?",
        (photo_id,),
    ).fetchone()


def listing(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ph.*, p.name AS uploader FROM photos ph LEFT JOIN people p ON p.id = ph.uploader_id "
        f"WHERE {where} ORDER BY ph.created_at DESC, ph.id",
        params,
    ).fetchall()


# On the screen with nobody in it named: not tagged by hand, no face Grandma named, and not "no one to name".
UNNAMED = (
    "status = 'approved' AND hidden = 0 AND no_one = 0"
    " AND NOT EXISTS (SELECT 1 FROM photo_people pp WHERE pp.photo_id = ph.id)"
    " AND NOT EXISTS (SELECT 1 FROM faces f JOIN face_groups g ON g.id = f.group_id"
    " WHERE f.photo_id = ph.id AND g.person_id IS NOT NULL)"
)


def unnamed_ids(conn: sqlite3.Connection) -> list[str]:
    return [r["id"] for r in listing(conn, UNNAMED)]


def pending_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM photos WHERE status = 'pending'").fetchone()[0]


def tags(conn: sqlite3.Connection, photo_id: str) -> set[int]:
    return {r[0] for r in conn.execute("SELECT person_id FROM photo_people WHERE photo_id = ?", (photo_id,))}


def face_names(conn: sqlite3.Connection, photo_id: str) -> list[str]:
    """People Grandma named among the faces in this photo."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT p.name FROM faces f JOIN face_groups g ON g.id = f.group_id JOIN people p ON p.id = g.person_id "
        "WHERE f.photo_id = ? ORDER BY p.name", (photo_id,))]


def set_tags(conn: sqlite3.Connection, photo_id: str, person_ids: set[int]) -> None:
    conn.execute("DELETE FROM photo_people WHERE photo_id = ?", (photo_id,))
    conn.executemany(
        "INSERT INTO photo_people (photo_id, person_id) SELECT ?, id FROM people WHERE id = ?",
        [(photo_id, pid) for pid in person_ids],
    )


def slideshow(conn: sqlite3.Connection, today: date) -> dict:
    """Photos on the screen: on someone's day only photos with them in, otherwise every approved photo."""
    # Someone remembered today counts too: their photos show, under a quiet title.
    celebrating = upcoming(conn, today, within_days=0, quiet=True)
    ids = [pid for c in celebrating for pid in c.person_ids]
    shown = "status = 'approved' AND hidden = 0"
    rows = []
    if ids:
        marks = ",".join("?" * len(ids))
        # Tagged by hand, or a face Grandma named.
        rows = conn.execute(
            f"SELECT id FROM photos WHERE {shown} AND id IN ("
            f" SELECT photo_id FROM photo_people WHERE person_id IN ({marks})"
            f" UNION SELECT f.photo_id FROM faces f JOIN face_groups g ON g.id = f.group_id"
            f"  WHERE g.person_id IN ({marks}))",
            ids + ids,
        ).fetchall()
    if not rows:
        rows = conn.execute(f"SELECT id FROM photos WHERE {shown}").fetchall()
    title = ""
    happy = [c for c in celebrating if not c.quiet]
    if happy:
        kinds = {c.event for c in happy}
        who = " & ".join(dict.fromkeys(c.name for c in happy))
        title = f"Happy {kinds.pop()}, {who}!" if len(kinds) == 1 else f"Celebrating {who} today!"
    elif celebrating:
        title = "Remembering " + " & ".join(dict.fromkeys(c.name for c in celebrating))
    return {"photos": [f"/photo-files/{r['id']}.jpg" for r in rows], "title": title}
