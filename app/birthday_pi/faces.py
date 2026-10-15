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
POLL_SECONDS = 10
HEARTBEAT = "faces_heartbeat"  # setting the app reads to tell whether the worker is running

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
    """Each group's summed embedding, so a new face joins the group whose average it's closest to."""

    def __init__(self, conn: sqlite3.Connection):
        self.sums: dict[int, np.ndarray] = {}
        for row in conn.execute("SELECT group_id, embedding FROM faces WHERE group_id IS NOT NULL"):
            vec = from_blob(row["embedding"])
            self.sums[row["group_id"]] = self.sums.get(row["group_id"], 0) + vec

    def nearest(self, feature: np.ndarray, exclude: set[int] = frozenset()) -> tuple[int | None, float]:
        ids = [i for i in self.sums if i not in exclude]
        if not ids:
            return None, 0.0
        means = np.array([self.sums[i] for i in ids])
        means /= np.linalg.norm(means, axis=1, keepdims=True)
        sims = means @ feature
        best = int(np.argmax(sims))
        return ids[best], float(sims[best])

    def assign(self, conn: sqlite3.Connection, feature: np.ndarray, exclude: set[int] = frozenset()) -> int:
        """exclude: groups already used in this photo, since nobody appears twice in one photo."""
        group_id, sim = self.nearest(feature, exclude)
        if group_id is None or sim < MATCH:
            group_id = conn.execute("INSERT INTO face_groups DEFAULT VALUES").lastrowid
            self.sums[group_id] = np.zeros_like(feature)
        self.sums[group_id] = self.sums[group_id] + feature
        return group_id


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
            group_id = groups.assign(conn, feature, used)
            used.add(group_id)
            x, y, w, h = (int(round(v)) for v in det[:4])
            face_id = conn.execute(
                "INSERT INTO faces (photo_id, group_id, x, y, w, h, score, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (photo_id, group_id, x, y, w, h, float(det[14]), to_blob(feature)),
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


def scan_waiting(conn: sqlite3.Connection, finder: Finder) -> tuple[int, int]:
    """Scans every photo not looked at yet, oldest first. Returns (photos, faces)."""
    todo = [r["id"] for r in conn.execute("SELECT id FROM photos WHERE faces_scanned = 0 ORDER BY created_at, id")]
    if not todo:
        return 0, 0
    groups = Groups(conn)  # reloaded each round, since people can merge or split groups in the app
    faces = 0
    for photo_id in todo:
        faces += scan(conn, finder, photo_id, groups)
        db.set_setting(conn, HEARTBEAT, datetime.now().isoformat(timespec="seconds"))
    return len(todo), faces


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
