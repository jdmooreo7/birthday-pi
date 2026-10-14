from birthday_pi import cli, db


def test_fresh_pi_sends_phones_to_setup_and_monitor_shows_welcome(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/setup"
    screen = client.get("/screen").text
    assert "Let's meet your family." in screen
    assert "<svg" in screen  # QR code
    assert "birthdaypi.local:8080/setup" in screen


def test_setup_validates_pin(client):
    r = client.post("/setup", data={"owner_name": "Grandma", "pin": "12", "pin2": "12"})
    assert r.status_code == 400 and "exactly 4 numbers" in r.text
    r = client.post("/setup", data={"owner_name": "Grandma", "pin": "1234", "pin2": "4321"})
    assert r.status_code == 400 and "don&#39;t match" in r.text


def test_setup_then_pick_grandma_needs_pin(client):
    r = client.post("/setup", data={"owner_name": "Nana", "pin": "2468", "pin2": "2468"}, follow_redirects=False)
    assert r.headers["location"] == "/who"
    assert client.get("/setup", follow_redirects=False).headers["location"] == "/"
    who = client.get("/who").text
    assert "Nana" in who and "asks for PIN" in who
    owner_id = db.owner(db.connect())["id"]
    r = client.post("/who", data={"person_id": owner_id}, follow_redirects=False)
    assert r.headers["location"] == "/pin"
    assert client.get("/", follow_redirects=False).headers["location"] == "/who"  # not trusted yet
    r = client.post("/pin", data={"pin": "1111"})
    assert r.status_code == 400 and "isn&#39;t right" in r.text
    r = client.post("/pin", data={"pin": "2468"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    home = client.get("/").text
    assert "Nana" in home and "Let's add the family" in home


def test_someone_new_is_added_and_asked_for_birthday(set_up):
    client = set_up
    r = client.post("/who", data={"new_name": "Dana"}, follow_redirects=False)
    assert r.headers["location"].endswith("?welcome=1")
    page = client.get(r.headers["location"]).text
    assert "Hi Dana!" in page
    assert "Dana · " in client.get("/").text
    assert "2 people need a birthday" in client.get("/").text  # Dana and Grandma


def test_add_person_with_birthday_and_anniversary(set_up):
    client = set_up
    client.post("/people/new", data={"name": "Sam", "birth_month": "3", "birth_day": "9", "birth_year": "1984"})
    sam_id = db.connect().execute("SELECT id FROM people WHERE name = 'Sam'").fetchone()[0]
    r = client.post("/people/new", data={"name": "Dana", "birth_month": "7", "birth_day": "1",
                                         "partner_id": str(sam_id), "ann_month": "9", "ann_day": "9", "ann_year": "2013"},
                    follow_redirects=False)
    assert r.status_code == 303
    everyone = client.get("/people").text
    assert "March 9" in everyone and "Anniversary with Sam · September 9" in everyone
    home = client.get("/").text
    assert "Sam &amp; Dana" in home and "Sep 9" in home


def test_person_form_rejects_bad_dates(set_up):
    client = set_up
    r = client.post("/people/new", data={"name": "Leo", "birth_month": "2", "birth_day": "30"})
    assert r.status_code == 400 and "February doesn&#39;t have a day 30" in r.text
    r = client.post("/people/new", data={"name": "Leo", "birth_month": "2"})
    assert r.status_code == 400 and "both the month and the day" in r.text
    r = client.post("/people/new", data={"name": "", "ann_month": "1", "ann_day": "1"})
    assert "Please type a name" in r.text and "who the anniversary is with" in r.text


def test_remove_person_but_never_grandma(set_up):
    client = set_up
    client.post("/people/new", data={"name": "Ben"})
    conn = db.connect()
    ben = conn.execute("SELECT id FROM people WHERE name = 'Ben'").fetchone()[0]
    client.post(f"/people/{ben}/remove")
    assert conn.execute("SELECT COUNT(*) FROM people WHERE name = 'Ben'").fetchone()[0] == 0
    owner = db.owner(conn)["id"]
    client.post(f"/people/{owner}/remove")
    assert db.owner(conn) is not None


def test_monitor_home_lists_coming_up(set_up):
    client = set_up
    client.post("/people/new", data={"name": "Mia", "birth_month": "3", "birth_day": "14"})
    screen = client.get("/screen/content").text
    assert "Coming up" in screen and "Mia" in screen
    assert "Let's meet your family." not in screen


def test_reset_pin_untrusts_grandmas_devices(set_up, capsys):
    client = set_up
    assert client.get("/", follow_redirects=False).status_code == 200
    assert cli.main(["reset-pin", "--pin", "9999"]) == 0
    assert client.get("/", follow_redirects=False).headers["location"] == "/who"
    r = client.post("/pin", data={"pin": "9999"}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_load_sample_only_on_fresh_pi(client, capsys):
    assert cli.main(["load-sample"]) == 0
    assert "PIN is 1234" in capsys.readouterr().out
    assert cli.main(["load-sample"]) == 1
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 9
    assert "Aunt Rosa" in client.get("/screen/content").text
