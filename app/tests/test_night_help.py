from fastapi.testclient import TestClient


def _night(client):
    return client.get("/screen/content").headers["X-Screen-Night"]


def test_night_defaults_to_10pm_until_5am_mostly_dark(set_up):
    assert _night(set_up) == "22-5-0.85"
    assert 'data-night="22-5-0.85"' in set_up.get("/screen").text
    page = set_up.get("/settings/night").text
    assert "Only you can change this." in page and "10 pm" in page and "5 am" in page and ">Save<" in page


def test_grandma_changes_the_night_and_the_screen_follows(set_up):
    r = set_up.post("/settings/night", data={"on": "1", "start": "21", "end": "6", "level": "full"},
                    follow_redirects=False)
    assert r.headers["location"] == "/settings/night?saved=1"
    assert _night(set_up) == "21-6-1.0"
    assert "Saved." in set_up.get("/settings/night?saved=1").text
    set_up.post("/settings/night", data={"on": "0", "start": "21", "end": "6", "level": "full"})
    assert _night(set_up) == "off"
    set_up.post("/settings/night", data={"on": "1", "start": "7", "end": "7", "level": "nonsense"})
    assert _night(set_up) == "21-6-1.0"  # same hour twice and an unknown level are ignored


def test_only_grandma_can_change_the_night(set_up):
    from birthday_pi.main import app
    visitor = TestClient(app)
    visitor.post("/who", data={"new_name": "Dana"})
    page = visitor.get("/settings/night").text
    assert "Only Grandma can change this." in page and ">Save<" not in page
    r = visitor.post("/settings/night", data={"on": "0"}, follow_redirects=False)
    assert r.headers["location"] == "/pin"
    assert _night(set_up) == "22-5-0.85"


def test_help_shows_her_hours_and_who_to_call(set_up):
    page = set_up.get("/help").text
    assert "from 10 pm until 5 am" in page and "Add who to call" in page and "tel:" not in page
    set_up.post("/settings/helper", data={"name": "Sam", "phone": "(555) 010-2030"})
    set_up.post("/settings/night", data={"on": "0", "start": "22", "end": "5", "level": "mostly"})
    page = set_up.get("/help").text
    assert 'href="tel:5550102030"' in page and "Call Sam" in page and "stays bright all night" in page


def test_every_phone_page_links_to_help(set_up):
    assert 'href="/help"' in set_up.get("/").text
    assert 'href="/help"' in set_up.get("/people").text
    assert 'href="/settings/night"' in set_up.get("/").text  # Grandma's way in
