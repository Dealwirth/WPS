"""Tests des Add-on-Kerns: Engine und HA-Client ohne echten Home Assistant.

Die Engine spricht nur ueber eine schmale Client-Schnittstelle. Hier wird ein
leichter Doppelgaenger genutzt, der echte Zustaende liefert und Aufrufe
aufzeichnet – so laesst sich genau pruefen, *ob* und *was* geschaltet wird.
"""

from __future__ import annotations

import sys
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
    return {"entity_id": "", "state": str(value), "attributes": a, "last_updated": "2026-11-05T12:00:00+00:00"}


class FakeClient:
    """Minimaler HA-Ersatz: liefert Zustaende und merkt sich Dienstaufrufe."""

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


def _states(feed_in_w=0.0, storage=45.0, setpoint=52.0):
    return {
        "sensor.feed": _state(feed_in_w, "W"),
        "sensor.storage": _state(storage, "°C"),
        "number.ww": _state(setpoint, "°C", min=35, max=65, temperature=setpoint),
    }


def _engine(tmp_path, states, sources=None, **settings):
    client = FakeClient(states)
    eng = SolarFlowEngine(client, str(tmp_path))
    eng.load({})
    eng.sources = sources or {
        "feed_in": "sensor.feed",
        "ww_temp_number": "number.ww",
        "ww_storage_sensor": "sensor.storage",
    }
    if settings:
        for k, v in settings.items():
            setattr(eng.settings, k, v)
    return eng, client


@pytest.mark.asyncio
async def test_shadow_proposes_but_never_switches(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=3000.0))
    eng.settings.mode = "shadow"
    decision = await eng.async_run_cycle()
    assert decision.state.value == "boost"  # Vorschlag sichtbar
    assert decision.blocked is True  # aber gesperrt
    assert client.calls == []  # nichts geschaltet


@pytest.mark.asyncio
async def test_active_switches_number_setpoint(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=3000.0))
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    assert len(client.calls) == 1
    domain, service, data, entity_id = client.calls[0]
    assert (domain, service) == ("number", "set_value")
    assert data["value"] == 60.0  # Boost-Temperatur
    assert entity_id == "number.ww"


@pytest.mark.asyncio
async def test_returns_to_normal_when_surplus_gone(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=0.0))
    eng.settings.mode = "active"
    await eng.async_run_cycle()
    # Sollwert ist bereits 52 -> kein Schreiben noetig (keine Abweichung).
    assert client.calls == []
    assert eng.machine.state.value == "normal"


@pytest.mark.asyncio
async def test_emergency_stop_blocks_everything(tmp_path):
    eng, client = _engine(tmp_path, _states(feed_in_w=5000.0))
    eng.settings.mode = "active"
    await eng.set_emergency(True)
    # Not-Aus faehrt einmal sicher auf Normal und sperrt danach.
    assert any(c[0] == "number" for c in client.calls)
    client.calls.clear()
    decision = await eng.async_run_cycle()
    assert decision.blocked is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_core_module_cannot_be_disabled(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    ok, _msg = await eng.set_module("core", False)
    assert ok is False


@pytest.mark.asyncio
async def test_unknown_source_keys_are_ignored(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    await eng.set_sources({"feed_in": "sensor.feed", "boese": "x"})
    assert "boese" not in eng.sources
    assert eng.sources["feed_in"] == "sensor.feed"


def test_state_persists_between_loads(tmp_path):
    eng, _ = _engine(tmp_path, _states())
    eng.settings.ww_boost_temp = 59.0
    eng.sources = {"feed_in": "sensor.feed"}
    eng.save()
    eng2 = SolarFlowEngine(FakeClient({}), str(tmp_path))
    eng2.load({})
    assert eng2.settings.ww_boost_temp == 59.0
    assert eng2.sources["feed_in"] == "sensor.feed"


def test_client_value_and_catalog_helpers():
    c = HomeAssistantClient()
    c._states = {"sensor.a": _state(42.5, "W"), "sensor.b": _state("unavailable")}
    assert c.value("sensor.a") == 42.5
    assert c.value("sensor.b") is None
    assert c.value("sensor.none") is None
    cat = c.entity_catalog()
    assert {e["entity_id"] for e in cat} == {"sensor.a", "sensor.b"}
