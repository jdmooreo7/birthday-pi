"""Commands run on the Pi, e.g.  docker compose exec app python -m birthday_pi.cli reset-pin"""
import argparse
import getpass
import sys
from datetime import date, timedelta

from . import PRODUCT, db, devices, pins

USAGE = """\
  reset-pin            Choose a new PIN for Grandma (asks twice). Her phones must enter it again.
  load-sample [--pin]  Set up a fresh Pi with a sample family for testing (PIN 1234 unless given).
  pilot-stats [--days] Numbers for the weekly pilot check: reminders, photos, faces. No names or dates.
"""


def reset_pin(args) -> int:
    conn = db.connect()
    if not db.is_set_up(conn):
        print(f"{PRODUCT} isn't set up yet. Open the setup page on a phone instead.")
        return 1
    pin = args.pin
    if pin is None:
        pin = getpass.getpass("New 4-digit PIN: ")
        if pin != getpass.getpass("Type it again: "):
            print("The two PINs don't match. Nothing changed.")
            return 1
    if not pins.is_valid(pin):
        print("The PIN must be exactly 4 numbers. Nothing changed.")
        return 1
    pins.set_pin(conn, pin)
    n = devices.untrust_all(conn)
    print(f"PIN changed. {n} device(s) will ask for the new PIN.")
    return 0


def load_sample(args) -> int:
    conn = db.connect()
    if db.is_set_up(conn):
        print("This Pi is already set up. The sample family only goes on a fresh Pi.")
        return 1
    pin = args.pin or "1234"
    if not pins.is_valid(pin):
        print("The PIN must be exactly 4 numbers.")
        return 1
    today = date.today()

    def soon(days: int) -> tuple[int, int]:
        d = today + timedelta(days=days)
        return d.month, d.day

    # Dates relative to today so reminders (milestone 2) have something to show straight away.
    people = [
        ("Grandma", 1, (6, 2), 1948),
        ("Aunt Rosa", 0, soon(0), 1961),
        ("Leo", 0, soon(7), 2016),
        ("Mia", 0, soon(14), 2019),
        ("Grandpa Joe", 0, soon(60), 1946),
        ("Dana", 0, soon(100), 1985),
        ("Sam", 0, soon(150), 1984),
        ("Uncle Ben", 0, None, None),
        ("Priya", 0, None, None),
    ]
    ids = {}
    for name, is_owner, md, year in people:
        month, day = md if md else (None, None)
        ids[name] = conn.execute(
            "INSERT INTO people (name, is_owner, birth_month, birth_day, birth_year) VALUES (?, ?, ?, ?, ?)",
            (name, is_owner, month, day, year),
        ).lastrowid
    for name, kind, days, year in (("Dana", "wedding", 25, 2013), ("Uncle Ben", "graduation", 40, 1990)):
        month, day = soon(days)
        conn.execute("INSERT INTO anniversaries (person_id, kind, month, day, year) VALUES (?, ?, ?, ?, ?)",
                     (ids[name], kind, month, day, year))
    n_photos = _sample_photos(conn, ids)
    pins.set_pin(conn, pin)
    db.set_setting(conn, "setup_complete", "1")
    print(f"Sample family loaded: {len(people)} people, {n_photos} drawn photos. Grandma's PIN is {pin}.")
    return 0


def pilot_stats(conn, today: date, days: int = 7) -> list[str]:
    """How the last `days` went, as numbers only, so the notes we take away hold nothing about the family."""
    import statistics
    from datetime import datetime, timezone

    from . import naming, reminders

    first_day = {name: start for name, start, *_ in reminders.STAGES}
    since = today - timedelta(days=days)
    lines = []
    pretend = db.get_setting(conn, "pretend_date")
    if pretend:
        lines.append("Note: a pretend date is on, so these numbers are for testing.")

    # "Got it": how long after a reminder first appeared (midnight of its first day) it was cleared.
    hours, same_day, early = [], 0, 0
    for key, acked_at in conn.execute("SELECT key, acked_at FROM reminder_acks"):
        _, stage, when = key.split(":")
        shown = date.fromisoformat(when) - timedelta(days=first_day[stage])
        acked = datetime.fromisoformat(acked_at).replace(tzinfo=timezone.utc).astimezone()
        if acked.date() <= since:
            continue
        h = (acked.replace(tzinfo=None) - datetime.combine(shown, datetime.min.time())).total_seconds() / 3600
        if h < 0:  # cleared before it was due: someone was testing with a pretend date
            early += 1
            continue
        hours.append(h)
        same_day += acked.date() == shown
    waiting = {r.key for r in reminders.active(conn, today)}
    missed = set()
    for i in range(1, days + 1):
        missed |= {r.key for r in reminders.active(conn, today - timedelta(days=i))} - waiting
    lines.append(f"Reminders cleared with Got it: {len(hours)} ({same_day} on the day they appeared)")
    if hours:
        lines.append(f"  hours from appearing to Got it: median {statistics.median(hours):.1f}, longest {max(hours):.1f}")
    if early:
        lines.append(f"  not counted: {early} cleared while testing with a pretend date")
    lines.append(f"Reminders showing now: {len(waiting)}")
    lines.append(f"Reminders that ended without Got it: {len(missed)}")

    # Photos and faces: is Grandma keeping up on her own?
    pending = conn.execute("SELECT COUNT(*), MIN(created_at) FROM photos WHERE status = 'pending'").fetchone()
    oldest = ""
    if pending[0]:
        age = today - datetime.fromisoformat(pending[1]).replace(tzinfo=timezone.utc).astimezone().date()
        oldest = f" (oldest waiting {age.days} days)"
    added = conn.execute("SELECT COUNT(*) FROM photos WHERE created_at > ?", (since.isoformat(),)).fetchone()[0]
    lines.append(f"Photos added: {added}; waiting for Grandma's OK: {pending[0]}{oldest}")
    lines.append(f"Faces waiting for \"Is this ...?\": {len(naming.asking(conn))}")
    lines.append(f"People in {PRODUCT}: {conn.execute('SELECT COUNT(*) FROM people').fetchone()[0]}")
    return lines


def show_pilot_stats(args) -> int:
    conn = db.connect()
    from .main import today
    print("\n".join(pilot_stats(conn, today(conn), args.days)))
    return 0


def _sample_photos(conn, ids: dict[str, int]) -> int:
    """Simple drawn "photos" with names on them, tagged, so the slideshow has something to show."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    from . import photos

    colours = ["#56697d", "#6b5d7d", "#5d7a6b", "#7d6a56", "#7d5660"]
    groups = [["Aunt Rosa"], ["Aunt Rosa", "Grandma"], ["Leo"], ["Leo", "Mia"], ["Mia"],
              ["Dana", "Sam"], ["Grandpa Joe", "Grandma"], ["Uncle Ben"]]
    font = ImageFont.load_default(size=110)
    for i, names in enumerate(groups):
        img = Image.new("RGB", (1600, 1000), colours[i % len(colours)])
        draw = ImageDraw.Draw(img)
        draw.text((800, 450), " & ".join(names), font=font, fill="#fdf6ec", anchor="mm")
        draw.text((800, 600), "sample photo", font=ImageFont.load_default(size=50), fill="#d9d2e6", anchor="mm")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        photo_id = photos.save_upload(conn, buf.getvalue(), ids["Grandma"], approved=True)
        photos.set_tags(conn, photo_id, {ids[n] for n in names})
    return len(groups)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="birthday_pi.cli", description=f"{PRODUCT} commands",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=USAGE)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("reset-pin", help="choose a new PIN for Grandma")
    p.add_argument("--pin", help=argparse.SUPPRESS)  # for scripts and tests
    p.set_defaults(func=reset_pin)
    p = sub.add_parser("load-sample", help="set up a fresh Pi with a sample family")
    p.add_argument("--pin", help="Grandma's PIN for the sample (default 1234)")
    p.set_defaults(func=load_sample)
    p = sub.add_parser("pilot-stats", help="numbers for the weekly pilot check")
    p.add_argument("--days", type=int, default=7, help="how many days back (default 7)")
    p.set_defaults(func=show_pilot_stats)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
