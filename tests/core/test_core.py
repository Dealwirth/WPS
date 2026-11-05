"""Tests des HA-freien Rechenkerns.

Diese Tests laufen ohne Home Assistant und prüfen genau den Pfad, der später
Geräte schaltet: Datenqualität, Grenzen, Schutz-Ebenen und das Ausführungs-Gate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_PARENT = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(CORE_PARENT))

from core.limits import clamp, validate_setpoint, validate_settings
from core.models import Action, Mode, Reading, Settings
from core.quality import check_freshness, check_jump, check_value
from core.safety import SafetyContext, evaluate_layers, gate


def r(value, age=5.0, available=True):
    return Reading(entity_id="sensor.x", value=value, age_s=age, available=available)


class TestQuality(unittest.TestCase):
    def test_freshness_ok(self):
        ok, _, _ = check_freshness(r(1000, age=10), 300)
        self.assertTrue(ok)

    def test_freshness_stale(self):
        ok, _, _ = check_freshness(r(1000, age=999), 300)
        self.assertFalse(ok)

    def test_freshness_unavailable(self):
        ok, _, _ = check_freshness(r(1000, available=False), 300)
        self.assertFalse(ok)

    def test_value_range(self):
        self.assertTrue(check_value(1000, lo=-30000, hi=30000)[0])
        self.assertFalse(check_value(1e9, lo=-30000, hi=30000)[0])
        self.assertFalse(check_value(None, lo=-1, hi=1)[0])

    def test_jump(self):
        self.assertTrue(check_jump(1000, 1100, 20000)[0])
        self.assertFalse(check_jump(25000, 0, 20000)[0])


class TestLimits(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(99, 0, 10), 10)
        self.assertEqual(clamp(5, 10, 0), 5)  # getauschte Grenzen

    def test_setpoint_never_exceeds_device(self):
        self.assertEqual(validate_setpoint(80, device_min=10, device_max=60), 60)
        self.assertEqual(validate_setpoint(5, device_min=10, device_max=60), 10)

    def test_validate_settings_fixes_hysteresis(self):
        s = Settings(feed_in_on_w=1000, feed_in_off_w=1500)
        s, notes = validate_settings(s)
        self.assertLess(s.feed_in_off_w, s.feed_in_on_w)
        self.assertTrue(notes)

    def test_validate_settings_clamps_values(self):
        s = Settings(ww_hysteresis_c=99, max_grid_import_w=999999)
        s, _ = validate_settings(s)
        self.assertLessEqual(s.ww_hysteresis_c, 15)
        self.assertLessEqual(s.max_grid_import_w, 60000)


class TestGate(unittest.TestCase):
    def ctx(self, mode=Mode.ACTIVE, emergency=False, feed=2000, age=5):
        return SafetyContext(
            feed_in=r(feed, age=age),
            settings=Settings(mode=mode),
            now=0,
            emergency_stop=emergency,
            mode=mode,
        )

    def test_gate_blocks_in_shadow(self):
        acts, reasons = gate(
            [Action("switch.x", "switch.turn_on", {})], self.ctx(mode=Mode.SHADOW)
        )
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_blocks_on_emergency(self):
        acts, reasons = gate([Action("switch.x", "switch.turn_on", {})], self.ctx(mode=Mode.ACTIVE, emergency=True))
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_blocks_stale(self):
        acts, reasons = gate([Action("switch.x", "switch.turn_on", {})], self.ctx(mode=Mode.ACTIVE, age=999))
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_clamps_temperature(self):
        acts, reasons = gate(
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 99})], self.ctx(mode=Mode.ACTIVE)
        )
        self.assertFalse(reasons)
        self.assertEqual(acts[0].data["temperature"], 60)

    def test_gate_allows_safe_action(self):
        acts, reasons = gate([Action("switch.x", "switch.turn_on", {})], self.ctx(mode=Mode.ACTIVE))
        self.assertEqual(len(acts), 1)
        self.assertFalse(reasons)


class TestLayers(unittest.TestCase):
    def test_ten_layers(self):
        ctx = SafetyContext(feed_in=r(2000), settings=Settings(mode=Mode.ACTIVE), now=0)
        layers = evaluate_layers(ctx)
        self.assertEqual(len(layers), 10)
        self.assertEqual([ly.idx for ly in layers], list(range(1, 11)))

    def test_emergency_layer_blocked(self):
        ctx = SafetyContext(feed_in=r(2000), settings=Settings(), now=0, emergency_stop=True)
        layers = evaluate_layers(ctx)
        self.assertEqual(layers[-1].status, "blocked")


if __name__ == "__main__":
    unittest.main()
