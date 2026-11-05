"""Tests für den Geräte-Store: Vorlagen, Strategien und Erkennung."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_PARENT = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(CORE_PARENT))

from core.devices import (
    DEVICE_TYPES,
    IMAGE_IDS,
    TYPES_BY_ID,
    DeviceContext,
    DeviceEntity,
    assess,
    clamp_device_settings,
    detect_device_types,
    device_view,
    group_by_device,
    make_device,
    missing_required_roles,
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

    def test_every_type_has_image_and_accent(self):
        for t in DEVICE_TYPES:
            self.assertTrue(t.image, t.type_id)
            self.assertTrue(t.accent, t.type_id)
            self.assertIn(t.image, IMAGE_IDS, t.type_id)

    def test_image_in_card(self):
        cards = {c["type_id"]: c for c in type_cards()}
        self.assertEqual(cards["wallbox"]["image"], "wallbox")
        self.assertEqual(cards["heat_pump"]["accent"], "amber")

    def test_device_image_override(self):
        d = make_device("wallbox", image="ev_charger")
        self.assertEqual(device_view(d)["image"], "ev_charger")
        d2 = make_device("wallbox")
        self.assertEqual(device_view(d2)["image"], "wallbox")

    def test_device_accent_override(self):
        d = make_device("wallbox", accent="pink")
        self.assertEqual(device_view(d)["accent"], "pink")
        d2 = make_device("wallbox")
        self.assertEqual(device_view(d2)["accent"], "teal")


class TestAutoDetect(unittest.TestCase):
    def test_detects_wallbox(self):
        entities = [
            EntityInfo("switch.wallbox_charge", "switch", "Wallbox laden"),
            EntityInfo("sensor.wallbox_power", "sensor", "Wallbox Leistung", unit="W"),
        ]
        found = detect_device_types(DEVICE_TYPES, entities, name_hint="Wallbox")
        ids = [d.type_id for d in found]
        self.assertIn("wallbox", ids)

    def test_requires_all_required_roles(self):
        """Ohne Schalter darf keine schaltbare Vorlage entstehen."""
        entities = [EntityInfo("sensor.x_power", "sensor", "Leistung", unit="W")]
        found = detect_device_types(DEVICE_TYPES, entities)
        self.assertNotIn("wallbox", [d.type_id for d in found])

    def test_empty_entities(self):
        self.assertEqual(detect_device_types(DEVICE_TYPES, []), [])

    def test_detects_heat_pump(self):
        entities = [
            EntityInfo("sensor.vitocal_speicher", "sensor", "WW Speichertemperatur", unit="°C"),
            EntityInfo("number.vitocal_ww_soll", "number", "WW Solltemperatur", unit="°C"),
        ]
        found = detect_device_types(DEVICE_TYPES, entities, name_hint="Vitocal")
        self.assertIn("heat_pump", [d.type_id for d in found])

    def test_sorted_by_confidence(self):
        entities = [
            EntityInfo("switch.wallbox", "switch", "Wallbox laden"),
            EntityInfo("sensor.wallbox_power", "sensor", "Wallbox Leistung", unit="W"),
            EntityInfo("sensor.wallbox_soc", "sensor", "Wallbox Ladestand", unit="%"),
        ]
        found = detect_device_types(DEVICE_TYPES, entities)
        conf = [d.confidence for d in found]
        self.assertEqual(conf, sorted(conf, reverse=True))


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

    def test_domain_alone_is_not_enough(self):
        """Ein reiner Domänen-Treffer darf keine Rolle belegen."""
        spec = TYPES_BY_ID["wallbox"]
        entities = [EntityInfo("sensor.feed_in", "sensor", "Einspeisung", unit="W")]
        sug = {s.key: s for s in suggest_roles(spec, entities)}
        self.assertIsNone(sug["soc"].entity_id)

    def test_missing_required_roles(self):
        dev = make_device("wallbox", roles={"power": "sensor.p"})
        self.assertEqual(missing_required_roles(dev), ["switch"])
        dev.roles["switch"] = "switch.w"
        self.assertEqual(missing_required_roles(dev), [])


class TestRegistry(unittest.TestCase):
    def test_groups_by_device(self):
        entities = [
            DeviceEntity("switch.wb1", "switch", "Wallbox 1", device_id="d1"),
            DeviceEntity("sensor.wb1_power", "sensor", "Leistung", device_id="d1", unit="W"),
            DeviceEntity("switch.wb2", "switch", "Wallbox 2", device_id="d2"),
            DeviceEntity("sensor.lonely", "sensor", "Ohne Gerät"),
        ]
        devices = {"d1": {"name": "Wallbox Eins"}, "d2": {"name": "Wallbox Zwei"}}
        groups = group_by_device(entities, devices, {})
        names = [g.name for g in groups]
        self.assertIn("Wallbox Eins", names)
        self.assertIn("Wallbox Zwei", names)
        self.assertEqual(names[-1], "Ohne Gerät")
        first = next(g for g in groups if g.key == "d1")
        self.assertEqual(len(first.entities), 2)

    def test_hidden_and_disabled_are_skipped(self):
        entities = [
            DeviceEntity("switch.a", "switch", "A", device_id="d1"),
            DeviceEntity("switch.b", "switch", "B", device_id="d1", disabled=True),
            DeviceEntity("switch.c", "switch", "C", device_id="d1", hidden=True),
        ]
        groups = group_by_device(entities, {"d1": {"name": "Gerät"}}, {})
        self.assertEqual([e.entity_id for e in groups[0].entities], ["switch.a"])

    def test_area_name_is_resolved(self):
        entities = [DeviceEntity("switch.a", "switch", "A", device_id="d1", area_id="a1")]
        groups = group_by_device(entities, {"d1": {"name": "Gerät"}}, {"a1": "Keller"})
        self.assertEqual(groups[0].area, "Keller")


if __name__ == "__main__":
    unittest.main()
