"""Which family member is using this phone or tablet, remembered with a cookie."""
import hashlib
import secrets
import sqlite3

from fastapi import Request
from fastapi.responses import Response

COOKIE = "bp_device"
TEN_YEARS = 10 * 365 * 24 * 3600


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current(conn: sqlite3.Connection, request: Request) -> sqlite3.Row | None:
    """The device row joined with its person, or None if this device hasn't picked a name."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = conn.execute(
        "SELECT d.token_hash, d.trusted_owner, p.id AS person_id, p.name, p.is_owner "
        "FROM devices d JOIN people p ON p.id = d.person_id WHERE d.token_hash = ?",
        (_hash(token),),
    ).fetchone()
    if row:
        conn.execute("UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE token_hash = ?", (row["token_hash"],))
    return row


def is_trusted_owner(device: sqlite3.Row | None) -> bool:
    return bool(device and device["is_owner"] and device["trusted_owner"])


def remember(conn: sqlite3.Connection, request: Request, response: Response, person_id: int, trusted_owner: bool) -> None:
    """Link this device to a person, issuing a cookie if it doesn't have one yet."""
    token = request.cookies.get(COOKIE) or secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO devices (token_hash, person_id, trusted_owner, last_seen) VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(token_hash) DO UPDATE SET person_id = excluded.person_id, "
        "trusted_owner = excluded.trusted_owner, last_seen = CURRENT_TIMESTAMP",
        (_hash(token), person_id, int(trusted_owner)),
    )
    response.set_cookie(COOKIE, token, max_age=TEN_YEARS, httponly=True, samesite="lax")


def untrust_all(conn: sqlite3.Connection) -> int:
    """Used by PIN reset: every device trusted as Grandma has to enter the new PIN."""
    cur = conn.execute("UPDATE devices SET trusted_owner = 0, person_id = NULL WHERE trusted_owner = 1")
    return cur.rowcount
