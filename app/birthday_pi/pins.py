"""Grandma's 4-digit PIN: hashed storage and a short lockout after wrong guesses."""
import hashlib
import hmac
import os
import re
import sqlite3
import time

from .db import get_setting, set_setting

MAX_TRIES = 5
LOCK_SECONDS = 60


def is_valid(pin: str) -> bool:
    return re.fullmatch(r"\d{4}", pin or "") is not None


def _hash(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1)


def set_pin(conn: sqlite3.Connection, pin: str) -> None:
    salt = os.urandom(16)
    set_setting(conn, "pin_hash", salt.hex() + "$" + _hash(pin, salt).hex())
    set_setting(conn, "pin_failures", "0")
    set_setting(conn, "pin_locked_until", "0")


def seconds_locked(conn: sqlite3.Connection, now: float | None = None) -> int:
    now = time.time() if now is None else now
    return max(0, int(float(get_setting(conn, "pin_locked_until", "0")) - now + 0.999))


def check_pin(conn: sqlite3.Connection, pin: str, now: float | None = None) -> str:
    """Returns "ok", "wrong" or "locked"."""
    now = time.time() if now is None else now
    if seconds_locked(conn, now):
        return "locked"
    stored = get_setting(conn, "pin_hash")
    if stored and is_valid(pin):
        salt, digest = stored.split("$")
        if hmac.compare_digest(_hash(pin, bytes.fromhex(salt)), bytes.fromhex(digest)):
            set_setting(conn, "pin_failures", "0")
            return "ok"
    failures = int(get_setting(conn, "pin_failures", "0")) + 1
    if failures >= MAX_TRIES:
        failures = 0
        set_setting(conn, "pin_locked_until", str(now + LOCK_SECONDS))
    set_setting(conn, "pin_failures", str(failures))
    return "wrong"
