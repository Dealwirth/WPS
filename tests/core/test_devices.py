"""Tests für den Geräte-Store: Vorlagen, Strategien und Erkennung."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_PARENT = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(CORE_PARENT))

from core.devices import (
    DEVICE_TYPES,
    TYPES_BY_ID,
    DeviceContext,
    assess,
    clamp_device_settings,
    make_device,
    suggest_roles,
    type_cards,
)
from core.discovery import EntityInfo
from core.models import Reading


def r(value, age=5.0):
    return Reading(entity_id="sensor.x", value=value, age_s=age)


def ctx_for(device, *, feed=0.0, surplus_ok=True, values=None, states=None, runtime_s=0.0):
    return DeviceContext(
        device=device,
        spec=TYPES_BY_ID[device.type_id],
        feed_in_w=feed,
        surplus_ok=surplus_ok,
        values=values or {},
        states=states or {},
        now=1000.0,
        runtime_s=runtime_s,
    )


class TestCatalog(unittest.TestCase):
    def test_unique_type_ids(self):
        ids = [t.type_id for t in DEVICE_TYPES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_strategies_exist(self):
        from core.devices.strategies import STRATEGIES

        for t in DEVICE_TYPES:
            self.assertIn(t.strategy, STRATEGIES, t.type_id)

    def test_required_roles_have_domains(self):
        for t in DEVICE_TYPES:
            for role in t.roles:
                self.assertTrue(role.domains, f"{t.type_id}.{role.key}")

    def test_type_cards_shape(self):
        cards = {c["type_id"]: c for c in type_cards()}
        self.assertIn("wallbox", cards)
        self.assertIn("roles", cards["wallbox"])
        self.assertIn("settings", cards["wallbox"])

    def test_wallbox_defaults_are_sane(self):
        d = make_device("wallbox")
        self.assertIsNotNone(d)
        self.assertGreater(d.settings["on_w"], d.settings["off_w"])

    def test_make_device_unknown_type(self):
        self.assertIsNone(make_device("does_not_exist"))


class TestClamp(unittest.TestCase):
    def test_clamps_out_of_range(self):
        d = make_device("wallbox")
        d.settings["on_w"] = 999999
        notes = clamp_device_settings(d)
        self.assertLessEqual(d.settings["on_w"], 20000)
        self.assertTrue(notes)

    def test_fixes_hysteresis(self):
        d = make_device("wallbox")
        d.settings["on_w"] = 1000
        d.settings["off_w"] = 2000
        clamp_device_settings(d)
        self.assertLess(d.settings["off_w"], d.settings["on_w"])

    def test_thermal_boost_above_normal(self):
        d = make_device("heat_pump")
        d.settings["normal_temp"] = 55
        d.settings["boost_temp"] = 50
        clamp_device_settings(d)
        self.assertGreaterEqual(d.settings["boost_temp"], d.settings["normal_temp"])


class TestSurplusSwitch(unittest.TestCase):
    def test_turns_on_with_surplus(self):
        d = make_device("wallbox", roles={"switch": "switch.wb"})
        a = assess(ctx_for(d, feed=6000, states={"switch": "off"}))
        self.assertTrue(any(x.service == "switch.turn_on" for x in a.actions))
        self.assertEqual(a.state, "charging")

    def test_stays_off_without_surplus(self):
        d = make_device("wallbox", roles={"switch": "switch.wb"})
        a = assess(ctx_for(d, feed=100, states={"switch": "off"}))
        self.assertEqual(a.actions, [])
        self.assertEqual(a.state, "idle")

    def test_turns_off_when_surplus_gone(self):
        d = make_device("wallbox", roles={"switch": "switch.wb"})
        a = assess(ctx_for(d, feed=100, states={"switch": "on"}, runtime_s=99999))
        self.assertTrue(any(x.service == "switch.turn_off" for x in a.actions))

    def test_min_runtime_holds(self):
        d = make_device("wallbox", roles={"switch": "switch.wb"})
        a = assess(ctx_for(d, feed=100, states={"switch": "on"}, runtime_s=10))
        self.assertEqual(a.actions, [])
        self.assertEqual(a.state, "holding")

    def test_target_soc_stops_charging(self):
        d = make_device("wallbox", roles={"switch": "switch.wb", "soc": "sensor.soc"})
        a = assess(ctx_for(d, feed=9000, states={"switch": "on"}, values={"soc": r(90)}))
        self.assertEqual(a.actions, [])
        self.assertEqual(a.state, "holding")

    def test_no_switch_blocks(self):
        d = make_device("wallbox")
        a = assess(ctx_for(d, feed=9000))
        self.assertEqual(a.state, "blocked")

    def test_bad_data_blocks(self):
        d = make_device("wallbox", roles={"switch": "switch.wb"})
        a = assess(ctx_for(d, feed=None, surplus_ok=False, states={"switch": "off"}))
        self.assertEqual(a.state, "blocked")


class TestThermalBoost(unittest.TestCase):
    def test_boost_writes_setpoint(self):
        d = make_device("heat_pump", roles={"setpoint": "number.ww", "storage": "sensor.st"})
        a = assess(ctx_for(d, feed=2500, values={"setpoint": r(52), "storage": r(45)}))
        self.assertEqual(a.details["target_temp"], 60)
        self.assertEqual(a.actions[0].data["value"], 60)

    def test_no_write_when_at_target(self):
        d = make_device("heat_pump", roles={"setpoint": "number.ww", "storage": "sensor.st"})
        a = assess(ctx_for(d, feed=2500, values={"setpoint": r(60), "storage": r(45)}))
        self.assertEqual(a.actions, [])

    def test_storage_warm_returns_normal(self):
        d = make_device("heat_pump", roles={"setpoint": "number.ww", "storage": "sensor.st"})
        a = assess(ctx_for(d, feed=2500, values={"setpoint": r(60), "storage": r(60)}))
        self.assertEqual(a.details["target_temp"], 52)
        self.assertTrue(a.actions)

    def test_water_heater_uses_temperature_field(self):
        d = make_device("heat_pump", roles={"setpoint": "water_heater.ww", "storage": "sensor.st"})
        a = assess(ctx_for(d, feed=2500, values={"setpoint": r(52), "storage": r(45)}))
        self.assertEqual(a.actions[0].service, "water_heater.set_temperature")
        self.assertIn("temperature", a.actions[0].data)

    def test_bad_data_safe_normal(self):
        d = make_device("heat_pump", roles={"setpoint": "number.ww", "storage": "sensor.st"})
        a = assess(ctx_for(d, feed=None, surplus_ok=False, values={"setpoint": r(60), "storage": r(45)}))
        self.assertEqual(a.state, "blocked")
        self.assertEqual(a.details["target_temp"], 52)


class TestBattery(unittest.TestCase):
    def test_battery_never_writes(self):
        d = make_device("battery", roles={"soc": "sensor.soc"})
        a = assess(ctx_for(d, values={"soc": r(10)}))
        self.assertEqual(a.actions, [])
        self.assertEqual(a.state, "holding")

    def test_battery_ready(self):
        d = make_device("battery", roles={"soc": "sensor.soc"})
        a = assess(ctx_for(d, values={"soc": r(80)}))
        self.assertEqual(a.state, "ready")


class TestDiscovery(unittest.TestCase):
    def test_suggests_roles(self):
        spec = TYPES_BY_ID["wallbox"]
        entities = [
            EntityInfo("switch.wallbox_charge", "switch", "Wallbox Laden"),
            EntityInfo("sensor.wallbox_power", "sensor", "Wallbox Power", unit="W"),
        ]
        sug = {s.key: s for s in suggest_roles(spec, entities)}
        self.assertEqual(sug["switch"].entity_id, "switch.wallbox_charge")
        self.assertEqual(sug["power"].entity_id, "sensor.wallbox_power")

    def test_no_entities_no_crash(self):
        spec = TYPES_BY_ID["heat_pump"]
        sug = suggest_roles(spec, [])
        self.assertTrue(all(s.entity_id is None for s in sug))


if __name__ == "__main__":
    unittest.main()
