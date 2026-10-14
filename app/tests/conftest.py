import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRTHDAY_PI_DATA", str(tmp_path))
    from birthday_pi.main import app
    return TestClient(app)


@pytest.fixture
def set_up(client):
    """A Pi that has finished setup, with this client picked as Grandma (trusted)."""
    client.post("/setup", data={"owner_name": "Grandma", "pin": "2468", "pin2": "2468"})
    client.post("/pin", data={"pin": "2468"})
    return client
