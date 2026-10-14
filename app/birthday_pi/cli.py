"""Commands run on the Pi, e.g.  docker compose exec app python -m birthday_pi.cli reset-pin"""
import argparse
import getpass
import sys
from datetime import date, timedelta

from . import db, devices, pins

USAGE = """\
  reset-pin            Choose a new PIN for Grandma (asks twice). Her phones must enter it again.
  load-sample [--pin]  Set up a fresh Pi with a sample family for testing (PIN 1234 unless given).
"""


def reset_pin(args) -> int:
    conn = db.connect()
    if not db.is_set_up(conn):
        print("Birthday Pi isn't set up yet. Open the setup page on a phone instead.")
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
    month, day = soon(25)
    a, b = sorted((ids["Dana"], ids["Sam"]))
    conn.execute("INSERT INTO anniversaries (person_a, person_b, month, day, year) VALUES (?, ?, ?, ?, 2013)",
                 (a, b, month, day))
    pins.set_pin(conn, pin)
    db.set_setting(conn, "setup_complete", "1")
    print(f"Sample family loaded: {len(people)} people. Grandma's PIN is {pin}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="birthday_pi.cli", description="Birthday Pi commands",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=USAGE)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("reset-pin", help="choose a new PIN for Grandma")
    p.add_argument("--pin", help=argparse.SUPPRESS)  # for scripts and tests
    p.set_defaults(func=reset_pin)
    p = sub.add_parser("load-sample", help="set up a fresh Pi with a sample family")
    p.add_argument("--pin", help="Grandma's PIN for the sample (default 1234)")
    p.set_defaults(func=load_sample)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
