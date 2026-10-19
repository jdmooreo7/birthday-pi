"""Naming faces (M6): Grandma names the groups of faces the faces worker found.

A group is asked about once its faces are in OFFERED_AT approved photos, biggest first. Naming links the
group to a person. Two groups named the same person both count as that person; nothing is merged, so
Undo just unlinks. A face taken out of a group ("isn't them") is left without a group, and the faces
worker places it elsewhere, never back in that group.
"""
import sqlite3

OFFERED_AT = 3
IGNORE_REASONS = {"not_family": "Not family", "not_person": "Not a person"}

# Approved photos only: faces in photos waiting for Grandma aren't offered until she approves them.
_GROUPS = """
    SELECT g.id, g.person_id, g.ignored, p.name, COUNT(DISTINCT f.photo_id) AS photos
    FROM face_groups g
    JOIN faces f ON f.group_id = g.id
    JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved'
    LEFT JOIN people p ON p.id = g.person_id
    {where}
    GROUP BY g.id ORDER BY photos DESC, g.id
"""


def group(conn: sqlite3.Connection, group_id: int) -> sqlite3.Row | None:
    return conn.execute(_GROUPS.format(where="WHERE g.id = ?"), (group_id,)).fetchone()


def to_name(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Groups still to ask about, biggest first."""
    rows = conn.execute(_GROUPS.format(where="WHERE g.person_id IS NULL AND g.ignored IS NULL")).fetchall()
    return [r for r in rows if r["photos"] >= OFFERED_AT]


def next_after(conn: sqlite3.Connection, group_id: int | None) -> int | None:
    """The group to ask about after this one (for Skip and Next person), wrapping round to the start."""
    ids = [g["id"] for g in to_name(conn)]
    if not ids:
        return None
    if group_id in ids:
        later = ids[ids.index(group_id) + 1:]
        if later:
            return later[0]
        return ids[0] if ids[0] != group_id else None
    return ids[0]


def face_ids(conn: sqlite3.Connection, group_id: int, limit: int | None = None) -> list[int]:
    """Faces in the group from approved photos, clearest first."""
    sql = ("SELECT f.id FROM faces f JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved' "
           "WHERE f.group_id = ? ORDER BY f.score DESC, f.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql, (group_id,))]


def take_out(conn: sqlite3.Connection, group_id: int, ids: list[int]) -> int:
    """Faces that aren't this person: the faces worker finds them another group."""
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return conn.execute(
        f"UPDATE faces SET group_id = NULL, not_group = ?, confirmed = 0 WHERE group_id = ? AND id IN ({marks})",
        (group_id, group_id, *ids),
    ).rowcount


def name(conn: sqlite3.Connection, group_id: int, person_id: int) -> None:
    """Grandma has looked at every face in the group, so they all count as confirmed."""
    conn.execute("UPDATE face_groups SET person_id = ?, ignored = NULL WHERE id = ?", (person_id, group_id))
    conn.execute("UPDATE faces SET confirmed = 1 WHERE group_id = ? AND photo_id IN "
                 "(SELECT id FROM photos WHERE status = 'approved')", (group_id,))


def unname(conn: sqlite3.Connection, group_id: int) -> None:
    conn.execute("UPDATE face_groups SET person_id = NULL WHERE id = ?", (group_id,))
    conn.execute("UPDATE faces SET confirmed = 0 WHERE group_id = ?", (group_id,))
    # Faces waiting to ask "Is this <them>?" go back to the faces worker to place.
    conn.execute("UPDATE faces SET ask_group = NULL WHERE ask_group = ?", (group_id,))


# ---------- M7: "Is this Leo?", "Not Leo", and forgetting a removed person ----------

_ASKING = """
    SELECT f.id, f.ask_group, g.person_id, p.name FROM faces f
    JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved'
    JOIN face_groups g ON g.id = f.ask_group JOIN people p ON p.id = g.person_id
    {where} ORDER BY f.id
"""


def asking(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Faces the worker wasn't sure about, oldest first: "Is this Leo?"."""
    return conn.execute(_ASKING.format(where="")).fetchall()


def ask(conn: sqlite3.Connection, face_id: int) -> sqlite3.Row | None:
    return conn.execute(_ASKING.format(where="WHERE f.id = ?"), (face_id,)).fetchone()


def answer(conn: sqlite3.Connection, face_id: int, yes: bool) -> None:
    """Yes: the face joins them, confirmed. No: the faces worker places it among the unnamed groups."""
    if yes:
        conn.execute("UPDATE faces SET group_id = ask_group, ask_group = NULL, confirmed = 1 "
                     "WHERE id = ? AND ask_group IS NOT NULL", (face_id,))
    else:
        conn.execute("UPDATE faces SET not_group = ask_group, ask_group = NULL, confirmed = 0 "
                     "WHERE id = ? AND ask_group IS NOT NULL", (face_id,))


def person_faces(conn: sqlite3.Connection, person_id: int) -> list[sqlite3.Row]:
    """Every face named as this person, in approved photos, clearest first."""
    return conn.execute(
        "SELECT f.id, f.group_id, f.confirmed FROM faces f JOIN face_groups g ON g.id = f.group_id "
        "JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved' "
        "WHERE g.person_id = ? ORDER BY f.score DESC, f.id", (person_id,)).fetchall()


def not_person(conn: sqlite3.Connection, person_id: int, ids: list[int]) -> int:
    """"Not Leo": the ticked faces leave Leo; the rest Grandma has now seen, so they count as confirmed."""
    shown = {r["id"]: r["group_id"] for r in person_faces(conn, person_id)}
    out = 0
    for face_id in ids:
        if face_id in shown:
            out += take_out(conn, shown[face_id], [face_id])
    kept = [i for i in shown if i not in ids]
    conn.executemany("UPDATE faces SET confirmed = 1 WHERE id = ?", [(i,) for i in kept])
    return out


def forget_person(conn: sqlite3.Connection, person_id: int) -> list[int]:
    """Before a person is removed: delete their faces (embeddings) and groups. Returns the face ids,
    so the caller can delete the crops. The photos themselves stay."""
    groups = [r[0] for r in conn.execute("SELECT id FROM face_groups WHERE person_id = ?", (person_id,))]
    if not groups:
        return []
    marks = ",".join("?" * len(groups))
    # Faces waiting for "Is this <them>?" go too: they're probably them.
    where = f"group_id IN ({marks}) OR ask_group IN ({marks})"
    face_ids = [r[0] for r in conn.execute(f"SELECT id FROM faces WHERE {where}", groups + groups)]
    conn.execute("BEGIN")
    conn.execute(f"DELETE FROM faces WHERE {where}", groups + groups)
    conn.execute(f"UPDATE faces SET not_group = NULL WHERE not_group IN ({marks})", groups)
    conn.execute(f"DELETE FROM face_groups WHERE id IN ({marks})", groups)
    conn.execute("COMMIT")
    return face_ids


def ignore(conn: sqlite3.Connection, group_id: int, reason: str) -> None:
    if reason in IGNORE_REASONS:
        conn.execute("UPDATE face_groups SET ignored = ?, person_id = NULL WHERE id = ?", (reason, group_id))


def set_aside(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Groups she set aside ("Not family", "Not a person"), biggest first, so she can name them after all.
    New faces like theirs kept joining them, so naming one picks those up too."""
    return conn.execute(_GROUPS.format(where="WHERE g.ignored IS NOT NULL")).fetchall()


def unignore(conn: sqlite3.Connection, group_id: int) -> None:
    """Undo, or "Name them after all": the group is asked about again."""
    conn.execute("UPDATE face_groups SET ignored = NULL WHERE id = ?", (group_id,))


def find_or_add_person(conn: sqlite3.Connection, typed: str) -> int:
    """A typed name that matches someone already in Birthday Pi is that person, not a new one."""
    row = conn.execute("SELECT id FROM people WHERE lower(name) = lower(?) ORDER BY id LIMIT 1", (typed,)).fetchone()
    if row:
        return row[0]
    return conn.execute("INSERT INTO people (name) VALUES (?)", (typed,)).lastrowid


def photo_count(conn: sqlite3.Connection, person_id: int, except_group: int | None = None) -> int:
    """Approved photos this person is in, by named faces or hand tags."""
    return conn.execute(
        "SELECT COUNT(*) FROM photos WHERE status = 'approved' AND id IN ("
        " SELECT f.photo_id FROM faces f JOIN face_groups g ON g.id = f.group_id"
        "  WHERE g.person_id = ? AND g.id IS NOT ?"
        " UNION SELECT photo_id FROM photo_people WHERE person_id = ?)",
        (person_id, except_group, person_id),
    ).fetchone()[0]


def named_people(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """People with named faces, most photos first."""
    return conn.execute(
        "SELECT p.id, p.name, COUNT(DISTINCT f.photo_id) AS photos FROM people p "
        "JOIN face_groups g ON g.person_id = p.id JOIN faces f ON f.group_id = g.id "
        "JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved' "
        "GROUP BY p.id ORDER BY photos DESC, p.name"
    ).fetchall()
