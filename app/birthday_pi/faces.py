"""Faces worker: finds faces in new photos and groups them by person.

Runs in its own container (the "faces" service in compose.yaml) with its own memory limit,
so a big import can't slow the app or the monitor. Run with: python -m birthday_pi.faces
It needs OpenCV and NumPy, which the app container doesn't have.
"""
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import db

MODELS = Path(os.environ.get("BIRTHDAY_PI_MODELS", "/models"))
MIN_FACE = 40  # px on the screen-sized photo; smaller faces are background people
MIN_SCORE = 0.8  # YuNet detection confidence
MATCH = 0.363  # SFace cosine similarity for "same person" (OpenCV Zoo's threshold)
# M7: a new face is named without asking only on a clear match to someone Grandma has confirmed 3 faces of.
# Measured on the family's 126 named faces (leave one out): 91% named this way, none wrongly.
AUTO = 0.5
AUTO_MARGIN = 0.1  # ahead of the next most likely named person by at least this much
AUTO_CONFIRMED = 3
POLL_SECONDS = 10
HEARTBEAT = "faces_heartbeat"  # setting the app reads to tell whether the worker is running
HEALTHY_WITHIN = 120  # seconds; the container is unhealthy if the heartbeat is older than this

log = logging.getLogger("faces")


def photo_path(photo_id: str) -> Path:
    return db.data_dir() / "photos" / f"{photo_id}.jpg"


def crop_path(face_id: int) -> Path:  # same as photos.face_crop_path; photos needs Pillow, which this container lacks
    return db.data_dir() / "faces" / f"{face_id}.jpg"


def to_blob(feature: np.ndarray) -> bytes:
    return feature.astype(np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class Groups:
    """Each group's summed embedding, so a new face joins the group whose average it's closest to.

    Named groups are compared per person (all of a person's groups together). A face that matches a named
    person joins them only on a clear match; otherwise it waits for Grandma ("Is this Leo?")."""

    def __init__(self, conn: sqlite3.Connection):
        self.sums: dict[int, np.ndarray] = {}
        self.sizes: dict[int, int] = {}
        for row in conn.execute("SELECT group_id, embedding FROM faces WHERE group_id IS NOT NULL"):
            vec = from_blob(row["embedding"])
            self.sums[row["group_id"]] = self.sums.get(row["group_id"], 0) + vec
            self.sizes[row["group_id"]] = self.sizes.get(row["group_id"], 0) + 1
        self.person_of = {r[0]: r[1] for r in conn.execute(
            "SELECT id, person_id FROM face_groups WHERE person_id IS NOT NULL") if r[0] in self.sums}
        self.confirmed = {r[0]: r[1] for r in conn.execute(
            "SELECT g.person_id, COUNT(*) FROM faces f JOIN face_groups g ON g.id = f.group_id "
            "WHERE g.person_id IS NOT NULL AND f.confirmed = 1 GROUP BY g.person_id")}

    def nearest(self, feature: np.ndarray, exclude: set[int] = frozenset(),
                named: bool = True) -> tuple[int | None, float, float]:
        """The closest group (for a named person, their biggest group), its similarity, and how far ahead
        it is of the closest other named person."""
        blocked = {self.person_of[g] for g in exclude if g in self.person_of}  # nobody twice in one photo
        candidates: dict[tuple, np.ndarray] = {}
        for g, total in self.sums.items():
            person = self.person_of.get(g)
            if person is None:
                if g not in exclude:
                    candidates[("group", g)] = total
            elif named and person not in blocked:
                candidates[("person", person)] = candidates.get(("person", person), 0) + total
        if not candidates:
            return None, 0.0, 0.0
        keys = list(candidates)
        means = np.array([candidates[k] for k in keys])
        means /= np.linalg.norm(means, axis=1, keepdims=True)
        sims = means @ feature
        best = int(np.argmax(sims))
        kind, key = keys[best]
        if kind == "group":
            return key, float(sims[best]), 0.0
        others = [float(s) for k, s in zip(keys, sims) if k[0] == "person" and k[1] != key]
        biggest = max((g for g, p in self.person_of.items() if p == key), key=lambda g: self.sizes.get(g, 0))
        return biggest, float(sims[best]), float(sims[best]) - max(others, default=0.0)

    def place(self, conn: sqlite3.Connection, feature: np.ndarray, exclude: set[int] = frozenset(),
              named: bool = True) -> tuple[int | None, int | None]:
        """Returns (group_id, ask_group): the group the face joins, or the named group to ask Grandma about.
        exclude: groups already used in this photo, since nobody appears twice in one photo.
        named=False keeps it out of named groups (a face Grandma said isn't someone)."""
        group_id, sim, margin = self.nearest(feature, exclude, named)
        person = self.person_of.get(group_id)
        if person is not None and sim >= MATCH:
            if sim >= AUTO and margin >= AUTO_MARGIN and self.confirmed.get(person, 0) >= AUTO_CONFIRMED:
                self._add(group_id, feature)
                return group_id, None
            return None, group_id
        if person is not None:  # not like anyone named: compare with the unnamed groups only
            group_id, sim, _ = self.nearest(feature, exclude, named=False)
        if group_id is None or sim < MATCH:
            group_id = conn.execute("INSERT INTO face_groups DEFAULT VALUES").lastrowid
            self.sums[group_id] = np.zeros_like(feature)
        self._add(group_id, feature)
        return group_id, None

    def _add(self, group_id: int, feature: np.ndarray) -> None:
        self.sums[group_id] = self.sums[group_id] + feature
        self.sizes[group_id] = self.sizes.get(group_id, 0) + 1


class Finder:
    """YuNet finds faces; SFace turns each one into an embedding."""

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(MODELS / "yunet.onnx"), "", (320, 320), MIN_SCORE)
        self.recognizer = cv2.FaceRecognizerSF.create(str(MODELS / "sface.onnx"), "")

    def find(self, path: Path) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]] | None:
        """(box and landmarks, aligned crop, unit-length embedding) per face, or None if unreadable."""
        img = self.cv2.imread(str(path))
        if img is None:
            return None
        h, w = img.shape[:2]
        self.detector.setInputSize((w, h))
        _, dets = self.detector.detect(img)
        found = []
        for det in dets if dets is not None else []:
            if min(det[2], det[3]) < MIN_FACE:
                continue
            crop = self.recognizer.alignCrop(img, det)
            feature = self.recognizer.feature(crop).flatten()
            found.append((det, crop, feature / np.linalg.norm(feature)))
        return found


def scan(conn: sqlite3.Connection, finder: Finder, photo_id: str, groups: Groups) -> int:
    """Finds and groups the faces in one photo. Returns how many were found."""
    found = finder.find(photo_path(photo_id)) or []
    crops, used = [], set()
    conn.execute("BEGIN")
    try:
        for det, crop, feature in found:
            group_id, ask_group = groups.place(conn, feature, used)
            used.add(group_id or ask_group)
            x, y, w, h = (int(round(v)) for v in det[:4])
            face_id = conn.execute(
                "INSERT INTO faces (photo_id, group_id, ask_group, x, y, w, h, score, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (photo_id, group_id, ask_group, x, y, w, h, float(det[14]), to_blob(feature)),
            ).lastrowid
            crops.append((face_id, crop))
        conn.execute("UPDATE photos SET faces_scanned = 1 WHERE id = ?", (photo_id,))
        conn.execute("COMMIT")
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK")  # the photo was deleted while we looked at it
        return 0
    (db.data_dir() / "faces").mkdir(parents=True, exist_ok=True)
    for face_id, crop in crops:
        finder.cv2.imwrite(str(crop_path(face_id)), crop)
    return len(found)


def regroup(conn: sqlite3.Connection, groups: Groups) -> int:
    """Places faces Grandma took out of a group ("isn't them") or said No to ("Is this Leo?"): never back
    in that group, nor in a group another face in the same photo is already in, and only among the unnamed
    groups, so she isn't asked about the same face again and again. Returns how many were placed."""
    loose = conn.execute(
        "SELECT id, photo_id, not_group, embedding FROM faces WHERE group_id IS NULL AND ask_group IS NULL ORDER BY id"
    ).fetchall()
    for face in loose:
        taken = {r[0] for r in conn.execute(
            "SELECT COALESCE(group_id, ask_group) FROM faces WHERE photo_id = ? AND id != ? "
            "AND COALESCE(group_id, ask_group) IS NOT NULL", (face["photo_id"], face["id"]))}
        exclude = taken | ({face["not_group"]} if face["not_group"] else set())
        conn.execute("BEGIN")
        group_id, _ = groups.place(conn, from_blob(face["embedding"]), exclude, named=False)
        conn.execute("UPDATE faces SET group_id = ? WHERE id = ?", (group_id, face["id"]))
        conn.execute("COMMIT")
    return len(loose)


def scan_waiting(conn: sqlite3.Connection, finder: Finder) -> tuple[int, int]:
    """Scans every photo not looked at yet, oldest first, then places any faces taken out of a group.
    Returns (photos, faces found)."""
    todo = [r["id"] for r in conn.execute("SELECT id FROM photos WHERE faces_scanned = 0 ORDER BY created_at, id")]
    loose = conn.execute("SELECT 1 FROM faces WHERE group_id IS NULL AND ask_group IS NULL LIMIT 1").fetchone()
    if not todo and not loose:
        return 0, 0
    groups = Groups(conn)  # reloaded each round, since Grandma can take faces out of groups in the app
    faces = 0
    for photo_id in todo:
        faces += scan(conn, finder, photo_id, groups)
        db.set_setting(conn, HEARTBEAT, datetime.now().isoformat(timespec="seconds"))
    regroup(conn, groups)
    return len(todo), faces


def healthy() -> bool:
    """For the container health check (selfcheck.py): has the worker written its heartbeat lately?"""
    conn = db.connect()
    try:
        beat = db.get_setting(conn, HEARTBEAT)
    finally:
        conn.close()
    return bool(beat) and (datetime.now() - datetime.fromisoformat(beat)).total_seconds() < HEALTHY_WITHIN


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    os.nice(10)  # the monitor and the app come first
    finder = Finder()
    log.info("faces worker started")
    while True:
        conn = db.connect()
        try:
            started = time.monotonic()
            photos, faces = scan_waiting(conn, finder)
            if photos:
                log.info("scanned %d photos, found %d faces in %.1fs", photos, faces, time.monotonic() - started)
            db.set_setting(conn, HEARTBEAT, datetime.now().isoformat(timespec="seconds"))
        finally:
            conn.close()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
