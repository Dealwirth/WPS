"""Smoke-Tests für die HTTP-API des Add-ons.

Diese Tests rufen die echten Routen über den aiohttp-TestClient auf und
fangen so Fehler wie fehlende Engine-Methoden ab.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

APP_DIR = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


class FakeClient:
    """Ersetzt den echten HA-Client – keine Netzwerkzugriffe im Test."""

    connected = True

    def __init__(self):
        self._states = {
            "sensor.feed": {"state": "0", "attributes": {"unit_of_measurement": "W"}},
            "switch.wb": {"state": "off", "attributes": {}},
        }

    async def start(self):
        return None

    async def stop(self):
        return None

    async def wait_connected(self, timeout=25.0):
        return None

    def state(self, entity_id):
        return self._states.get(entity_id)

    def value(self, entity_id):
        return None

    def entity_catalog(self):
        return [{"entity_id": e, "domain": e.split(".")[0], "name": e} for e in self._states]

    def add_state_callback(self, cb):
        return None

    async def fetch_registry(self):
        return {"devices": [], "entities": [], "areas": []}

    async def call_service(self, *args, **kwargs):
        return None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HomeAssistantClient", FakeClient)
    monkeypatch.setenv("SOLARFLOW_DATA_DIR", str(tmp_path))
    app = await server.create_app()
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    assert (await resp.json())["status"] == "ok"


async def test_snapshot(client):
    resp = await client.get("/api/snapshot")
    assert resp.status == 200
    data = await resp.json()
    assert "settings" in data and "device_types" in data


async def test_device_types(client):
    resp = await client.get("/api/device_types")
    assert resp.status == 200
    types = await resp.json()
    assert len(types) == 12
    assert {"type_id", "category", "roles", "settings"} <= set(types[0])


async def test_registry_endpoint(client):
    resp = await client.get("/api/devices/registry")
    assert resp.status == 200
    assert isinstance(await resp.json(), list)


async def test_entities_endpoint(client):
    resp = await client.get("/api/entities")
    assert resp.status == 200
    assert isinstance(await resp.json(), list)
