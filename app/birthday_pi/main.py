"""Birthday Pi web app: the monitor screen (/screen) and the phone pages (everything else)."""
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import segno
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, devices, pins
from .dates import MONTHS, how_far, missing_birthdays, short_date, upcoming, valid_month_day

HERE = Path(__file__).parent
PUBLIC_URL = os.environ.get("BIRTHDAY_PI_URL", "http://birthdaypi.local:8080").rstrip("/")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(MONTHS=MONTHS, how_far=how_far, short_date=short_date)


class RedirectTo(Exception):
    def __init__(self, url: str):
        self.url = url


@app.exception_handler(RedirectTo)
async def _redirect(request: Request, exc: RedirectTo) -> RedirectResponse:
    return RedirectResponse(exc.url, status_code=303)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def today() -> date:
    return date.today()


def require_setup(conn: sqlite3.Connection) -> None:
    if not db.is_set_up(conn):
        raise RedirectTo("/setup")


def require_device(conn: sqlite3.Connection, request: Request) -> sqlite3.Row:
    require_setup(conn)
    device = devices.current(conn, request)
    if device is None:
        raise RedirectTo("/who")
    return device


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status_code)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ---------- First-run setup ----------

@app.get("/setup")
def setup_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_set_up(conn):
        return RedirectResponse("/", status_code=303)
    return page(request, "setup.html", owner_name="Grandma", errors={})


@app.post("/setup")
async def setup_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_set_up(conn):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    owner_name = str(form.get("owner_name", "")).strip()
    pin, pin2 = str(form.get("pin", "")), str(form.get("pin2", ""))
    errors = {}
    if not owner_name:
        errors["owner_name"] = "Please type what the family calls her."
    elif len(owner_name) > 40:
        errors["owner_name"] = "Please use 40 letters or fewer."
    if not pins.is_valid(pin):
        errors["pin"] = "The PIN must be exactly 4 numbers."
    elif pin != pin2:
        errors["pin2"] = "The two PINs don't match. Please try again."
    if errors:
        return page(request, "setup.html", 400, owner_name=owner_name, errors=errors)
    conn.execute("INSERT INTO people (name, is_owner) VALUES (?, 1)", (owner_name,))
    pins.set_pin(conn, pin)
    db.set_setting(conn, "setup_complete", "1")
    return RedirectResponse("/who", status_code=303)


# ---------- Who's using this phone? ----------

@app.get("/who")
def who_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    people = conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name").fetchall()
    return page(request, "who.html", people=people, device=devices.current(conn, request), error=None)


@app.post("/who")
async def who_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    new_name = str(form.get("new_name", "")).strip()
    if new_name:
        if len(new_name) > 40:
            people = conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name").fetchall()
            return page(request, "who.html", 400, people=people, device=None, error="Please use 40 letters or fewer.")
        cur = conn.execute("INSERT INTO people (name) VALUES (?)", (new_name,))
        response = RedirectResponse(f"/people/{cur.lastrowid}?welcome=1", status_code=303)
        devices.remember(conn, request, response, cur.lastrowid, trusted_owner=False)
        return response
    try:
        person = conn.execute("SELECT * FROM people WHERE id = ?", (int(form.get("person_id", "")),)).fetchone()
    except ValueError:
        person = None
    if person is None:
        return RedirectResponse("/who", status_code=303)
    if person["is_owner"]:
        return RedirectResponse("/pin", status_code=303)
    response = RedirectResponse("/", status_code=303)
    devices.remember(conn, request, response, person["id"], trusted_owner=False)
    return response


@app.get("/pin")
def pin_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    return page(request, "pin.html", owner=db.owner(conn), error=None, locked=pins.seconds_locked(conn))


@app.post("/pin")
async def pin_check(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    result = pins.check_pin(conn, str(form.get("pin", "")))
    if result == "ok":
        response = RedirectResponse("/", status_code=303)
        devices.remember(conn, request, response, db.owner(conn)["id"], trusted_owner=True)
        return response
    locked = pins.seconds_locked(conn)
    error = None if locked else "That PIN isn't right. Please try again."
    return page(request, "pin.html", 400, owner=db.owner(conn), error=error, locked=locked)


# ---------- Phone home and people ----------

@app.get("/")
def home(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    people_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    return page(
        request, "home.html", device=device, today=today(),
        upcoming=upcoming(conn, today(), limit=6), missing=missing_birthdays(conn), people_count=people_count,
    )


def _people_list(conn: sqlite3.Connection) -> list[dict]:
    partners = {}
    for a in conn.execute(
        "SELECT a.*, pa.name AS name_a, pb.name AS name_b FROM anniversaries a "
        "JOIN people pa ON pa.id = a.person_a JOIN people pb ON pb.id = a.person_b"
    ):
        partners[a["person_a"]] = (a["name_b"], a)
        partners[a["person_b"]] = (a["name_a"], a)
    result = []
    for p in conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name"):
        birthday = f"{MONTHS[p['birth_month'] - 1]} {p['birth_day']}" if p["birth_month"] else None
        partner = partners.get(p["id"])
        anniversary = f"{partner[0]} · {MONTHS[partner[1]['month'] - 1]} {partner[1]['day']}" if partner else None
        result.append({"id": p["id"], "name": p["name"], "is_owner": p["is_owner"],
                       "birthday": birthday, "anniversary": anniversary})
    return result


@app.get("/people")
def people_list(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return page(request, "people.html", device=device, people=_people_list(conn))


def _anniversary_for(conn: sqlite3.Connection, person_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM anniversaries WHERE person_a = ? OR person_b = ?", (person_id, person_id)
    ).fetchone()


def _form_values(conn: sqlite3.Connection, person: sqlite3.Row | None) -> dict:
    if person is None:
        return {"name": "", "birth_month": "", "birth_day": "", "birth_year": "",
                "partner_id": "", "ann_month": "", "ann_day": "", "ann_year": ""}
    ann = _anniversary_for(conn, person["id"])
    partner_id = ""
    if ann:
        partner_id = ann["person_b"] if ann["person_a"] == person["id"] else ann["person_a"]

    def s(v):
        return "" if v is None else str(v)

    return {
        "name": person["name"], "birth_month": s(person["birth_month"]), "birth_day": s(person["birth_day"]),
        "birth_year": s(person["birth_year"]), "partner_id": s(partner_id),
        "ann_month": s(ann["month"]) if ann else "", "ann_day": s(ann["day"]) if ann else "",
        "ann_year": s(ann["year"]) if ann else "",
    }


def _parse_person_form(form, person_id: int | None, conn: sqlite3.Connection) -> tuple[dict, dict, dict]:
    """Returns (values to redisplay, cleaned data, errors)."""
    values = {k: str(form.get(k, "")).strip() for k in
              ("name", "birth_month", "birth_day", "birth_year", "partner_id", "ann_month", "ann_day", "ann_year")}
    errors: dict[str, str] = {}
    this_year = today().year

    def to_int(key):
        try:
            return int(values[key]) if values[key] else None
        except ValueError:
            errors[key] = "Please use numbers only."
            return None

    clean = {"name": values["name"]}
    if not values["name"]:
        errors["name"] = "Please type a name."
    elif len(values["name"]) > 40:
        errors["name"] = "Please use 40 letters or fewer."

    for prefix, month_key, day_key, year_key in (("birth", "birth_month", "birth_day", "birth_year"),
                                                 ("ann", "ann_month", "ann_day", "ann_year")):
        month, day, year = to_int(month_key), to_int(day_key), to_int(year_key)
        if (month is None) != (day is None):
            errors[day_key] = "Please pick both the month and the day."
        elif month is not None and not valid_month_day(month, day):
            errors[day_key] = f"{MONTHS[month - 1] if 1 <= month <= 12 else 'That month'} doesn't have a day {day}."
        if year is not None and not 1900 <= year <= this_year:
            errors[year_key] = f"Please use a year between 1900 and {this_year}."
        if year is not None and month is None:
            errors[day_key] = "Please pick the month and day too."
        clean[month_key], clean[day_key], clean[year_key] = month, day, year

    partner_id = to_int("partner_id")
    if partner_id is not None:
        if partner_id == person_id or conn.execute("SELECT 1 FROM people WHERE id = ?", (partner_id,)).fetchone() is None:
            errors["partner_id"] = "Please pick someone else."
        elif clean["ann_month"] is None and "ann_day" not in errors:
            errors["ann_day"] = "Please pick the anniversary month and day."
    elif clean["ann_month"] is not None:
        errors["partner_id"] = "Please pick who the anniversary is with."
    clean["partner_id"] = partner_id
    return values, clean, errors


def _save_person(conn: sqlite3.Connection, person_id: int | None, c: dict) -> int:
    if person_id is None:
        person_id = conn.execute(
            "INSERT INTO people (name, birth_month, birth_day, birth_year) VALUES (?, ?, ?, ?)",
            (c["name"], c["birth_month"], c["birth_day"], c["birth_year"]),
        ).lastrowid
    else:
        conn.execute(
            "UPDATE people SET name = ?, birth_month = ?, birth_day = ?, birth_year = ? WHERE id = ?",
            (c["name"], c["birth_month"], c["birth_day"], c["birth_year"], person_id),
        )
    # One partner each: replace any anniversary either person had before.
    ids = [person_id] + ([c["partner_id"]] if c["partner_id"] else [])
    for pid in ids:
        conn.execute("DELETE FROM anniversaries WHERE person_a = ? OR person_b = ?", (pid, pid))
    if c["partner_id"]:
        a, b = sorted((person_id, c["partner_id"]))
        conn.execute(
            "INSERT INTO anniversaries (person_a, person_b, month, day, year) VALUES (?, ?, ?, ?, ?)",
            (a, b, c["ann_month"], c["ann_day"], c["ann_year"]),
        )
    return person_id


def _person_page(request, conn, device, person, values, errors, status_code=200, welcome=False):
    others = conn.execute(
        "SELECT id, name FROM people WHERE id != ? ORDER BY name", (person["id"] if person else -1,)
    ).fetchall()
    return page(request, "person_form.html", status_code, device=device, person=person, values=values,
                errors=errors, others=others, welcome=welcome, this_year=today().year)


@app.get("/people/new")
def person_new(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return _person_page(request, conn, device, None, _form_values(conn, None), {})


@app.post("/people/new")
async def person_create(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    values, clean, errors = _parse_person_form(await request.form(), None, conn)
    if errors:
        return _person_page(request, conn, device, None, values, errors, 400)
    _save_person(conn, None, clean)
    return RedirectResponse("/people", status_code=303)


def _get_person(conn: sqlite3.Connection, person_id: int) -> sqlite3.Row:
    person = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if person is None:
        raise RedirectTo("/people")
    return person


@app.get("/people/{person_id}")
def person_edit(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    welcome = request.query_params.get("welcome") == "1"
    return _person_page(request, conn, device, person, _form_values(conn, person), {}, welcome=welcome)


@app.post("/people/{person_id}")
async def person_update(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    values, clean, errors = _parse_person_form(await request.form(), person_id, conn)
    if errors:
        return _person_page(request, conn, device, person, values, errors, 400)
    _save_person(conn, person_id, clean)
    return RedirectResponse("/people", status_code=303)


@app.get("/people/{person_id}/remove")
def person_remove_confirm(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    if person["is_owner"]:
        return RedirectResponse(f"/people/{person_id}", status_code=303)
    return page(request, "person_remove.html", device=device, person=person)


@app.post("/people/{person_id}/remove")
def person_remove(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_device(conn, request)
    person = _get_person(conn, person_id)
    if not person["is_owner"]:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
    return RedirectResponse("/people", status_code=303)


# ---------- Monitor ----------

def _screen_context(conn: sqlite3.Connection) -> dict:
    if not db.is_set_up(conn):
        qr = segno.make(PUBLIC_URL + "/setup", error="m")
        svg = qr.svg_inline(scale=10, border=2, dark="#1d1b2f", light="#fdf6ec")
        return {"mode": "welcome", "qr_svg": svg, "setup_url": PUBLIC_URL.split("://", 1)[-1] + "/setup"}
    return {"mode": "home", "today": today(), "upcoming": upcoming(conn, today(), limit=4),
            "missing_count": len(missing_birthdays(conn)), "now": datetime.now(),
            "phone_url": PUBLIC_URL.split("://", 1)[-1]}


@app.get("/screen")
def screen(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return page(request, "screen.html", **_screen_context(conn))


@app.get("/screen/content")
def screen_content(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    return page(request, "_screen_content.html", **_screen_context(conn))
