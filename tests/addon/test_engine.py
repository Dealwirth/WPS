"""Tests des Add-on-Kerns: Engine und HA-Client ohne echten Home Assistant.

Die Engine spricht nur über eine schmale Client-Schnittstelle. Hier wird ein
leichter Doppelgänger genutzt, der echte Zustände liefert und Aufrufe
aufzeichnet – so lässt sich genau prüfen, *ob* und *was* geschaltet wird.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(APP))

from engine import SolarFlowEngine
from ha_client import HomeAssistantClient


def _state(value, unit=None, **attrs):
    a = dict(attrs)
    if unit:
        a["unit_of_measurement"] = unit
    return {
        "entity_id": "",
        "state": str(value),
        "attributes": a,
        "last_updated": datetime.now(UTC).isoformat(),
    }


class FakeClient:
    """Minimaler HA-Ersatz: liefert Zustände und merkt sich Dienstaufrufe."""

    def __init__(self, states: dict[str, dict]):
        self._states = states
        self.connected = True
        self.calls: list[tuple[str, str, dict, str | None]] = []
        self.callbacks = []

    def state(self, entity_id):
        return self._states.get(entity_id)

    def value(self, entity_id):
        st = self._states.get(entity_id)
        try:
            return float(st["state"]) if st else None
        except (ValueError, TypeError):
            return None

    def entity_catalog(self):
        return [{"entity_id": e, "domain": e.split(".")[0], "name": e} for e in self._states]

    def add_state_callback(self, cb):
        self.callbacks.append(cb)

    async def call_service(self, domain, service, data, entity_id=None):
        self.calls.append((domain, service, data, entity_id))


def _states(feed_in_w=0.0, storage=45.0, setpoint=52.0, wallbox="off"):
    return {
        "sensor.feed": _state(feed_in_w, "W"),
        "sensor.storage": _state(storage, "°C"),
        "number.ww": _state(setpoint, "°C", min=35, max=65, temperature=setpoint),
        "switch.wallbox": _state(wallbox),
    }


def _engine(tmp_path, states):
    client = FakeClient(states)
    eng = SolarFlowEngine(client, str(tmp_path))
    eng.load({})
    eng.sources = {"feed_in": "sensor.feed"}
    return eng, client


def _add_heat_pump(eng):
    return eng.add_device(
        "heat_pump",
        name="Wärmepumpe",
        roles={"setpoint": "number.ww", "storage": "sensor.storage"},
    )


def _add_wallbox(eng):
    return eng.add_device("wallbox", name="Wallbox", roles={"switch": "switch.wallbox"})


@pytest.mark.asyncio
async def test_shadow_proposes_but_never_switches(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=3000.0))
    _add_heat_pump(eng)
    eng.settings.mode = "shadow"
    decision = await eng.async_run_cycle()
    assert decision.state.value == "boost"  # Vorschlag sichtbar
    assert decision.blocked is True  # aber gesperrt
    assert client.calls == []  # nichts geschaltet


@pytest.mark.asyncio
async def test_active_switches_number_setpoint(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=3000.0))
    _add_heat_pump(eng)
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    assert len(client.calls) == 1
    domain, service, data, entity_id = client.calls[0]
    assert (domain, service) == ("number", "set_value")
    assert data["value"] == 60.0  # Boost-Temperatur
    assert entity_id == "number.ww"


@pytest.mark.asyncio
async def test_wallbox_switches_on_with_surplus(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=6000.0, wallbox="off"))
    _add_wallbox(eng)
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    assert ("switch", "turn_on", {}, "switch.wallbox") in client.calls


@pytest.mark.asyncio
async def test_no_device_no_actions(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=6000.0))
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    assert client.calls == []


@pytest.mark.asyncio
async def test_disabled_device_is_ignored(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=6000.0, wallbox="off"))
    dev = _add_wallbox(eng)
    eng.update_device(dev.id, {"enabled": False})
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    assert client.calls == []


@pytest.mark.asyncio
async def test_emergency_stop_blocks_everything(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=5000.0))
    _add_heat_pump(eng)
    eng.settings.mode = "active"
    await eng.set_emergency(True)
    assert any(c[0] == "number" for c in client.calls)
    client.calls.clear()
    decision = await eng.async_run_cycle()
    assert decision.blocked is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_unknown_source_keys_are_ignored(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    await eng.set_sources({"feed_in": "sensor.feed", "boese": "x"})
    assert "boese" not in eng.sources
    assert eng.sources["feed_in"] == "sensor.feed"


def test_devices_persist_between_loads(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    dev = _add_wallbox(eng)
    eng.save()
    eng2 = SolarFlowEngine(FakeClient({}), str(tmp_path))
    eng2.load({})
    assert len(eng2.devices) == 1
    assert eng2.devices[0].id == dev.id
    assert eng2.devices[0].roles["switch"] == "switch.wallbox"


def test_legacy_sources_migrate_to_heat_pump(tmp_path):
    """Alte feste Quellen werden zu einem Wärmepumpen-Gerät."""
    state = {
        "sources": {
            "feed_in": "sensor.feed",
            "ww_temp_number": "number.ww",
            "ww_storage_sensor": "sensor.storage",
        },
        "settings": {},
    }
    (tmp_path / "state.json").write_text(__import__("json").dumps(state))
    eng = SolarFlowEngine(FakeClient({}), str(tmp_path))
    eng.load({})
    assert len(eng.devices) == 1
    assert eng.devices[0].type_id == "heat_pump"
    assert eng.devices[0].roles["setpoint"] == "number.ww"


def test_add_remove_device(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    dev = _add_wallbox(eng)
    assert len(eng.devices) == 1
    assert eng.remove_device(dev.id) is True
    assert eng.devices == []
    assert eng.remove_device(dev.id) is False


def test_client_value_and_catalog_helpers():
    c = HomeAssistantClient()
    c._states = {"sensor.a": _state(42.5, "W"), "sensor.b": _state("unavailable")}
    assert c.value("sensor.a") == 42.5
    assert c.value("sensor.b") is None
    assert c.value("sensor.none") is None
    cat = c.entity_catalog()
    assert {e["entity_id"] for e in cat} == {"sensor.a", "sensor.b"}
