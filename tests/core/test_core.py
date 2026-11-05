"""Tests des HA-freien Rechenkerns.

Diese Tests laufen ohne Home Assistant und prüfen genau den Pfad, der später
Geräte schaltet: Hysterese, Grenzen, Schutz-Ebenen und das Ausführungs-Gate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Den HA-freien Kern direkt importierbar machen: wir laden das Paket "core"
# aus dem Integrationsordner, ohne das (HA-abhängige) __init__.py der
# Integration auszuführen. So bleibt der Kern ohne Home Assistant testbar.
CORE_PARENT = Path(__file__).resolve().parents[2] / "solarflow" / "app"
sys.path.insert(0, str(CORE_PARENT))

from core.limits import clamp, validate_setpoint, validate_settings
from core.machine import Machine
from core.models import (
    Action,
    Mode,
    PlantState,
    Reading,
    Settings,
)
from core.planner import evaluate
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

    def test_validate_settings_boost_above_normal(self):
        s = Settings(ww_boost_temp=45, ww_normal_temp=52)
        s, _ = validate_settings(s)
        self.assertGreaterEqual(s.ww_boost_temp, s.ww_normal_temp)

    def test_validate_settings_fixes_wallbox_hysteresis(self):
        s = Settings(wallbox_on_w=2000, wallbox_off_w=3000)
        s, notes = validate_settings(s)
        self.assertLess(s.wallbox_off_w, s.wallbox_on_w)
        self.assertTrue(notes)

    def test_validate_settings_clamps_new_values(self):
        s = Settings(ww_hysteresis_c=99, wallbox_min_charge_a=99, heating_shift_c=99, forecast_horizon_h=999)
        s, _ = validate_settings(s)
        self.assertLessEqual(s.ww_hysteresis_c, 15)
        self.assertLessEqual(s.wallbox_min_charge_a, 32)
        self.assertLessEqual(s.heating_shift_c, 10)
        self.assertLessEqual(s.forecast_horizon_h, 72)


class TestMachine(unittest.TestCase):
    def test_no_boost_without_surplus(self):
        m = Machine()
        state, changed, _ = m.update(now=0, feed_in_w=100, data_ok=True, demand=True, settings=Settings())
        self.assertEqual(state, PlantState.NORMAL)
        self.assertFalse(changed)

    def test_boost_on_surplus(self):
        m = Machine()
        state, changed, _ = m.update(now=0, feed_in_w=2000, data_ok=True, demand=True, settings=Settings())
        self.assertEqual(state, PlantState.BOOST)
        self.assertTrue(changed)

    def test_hysteresis_prevents_quick_off(self):
        m = Machine()
        s = Settings(feed_in_on_w=1800, feed_in_off_w=900, min_runtime_min=15)
        m.update(now=0, feed_in_w=2000, data_ok=True, demand=True, settings=s)
        # Nach 1 Minute unter Ausschaltschwelle, aber Mindestlaufzeit nicht erreicht
        state, changed, _ = m.update(now=60, feed_in_w=500, data_ok=True, demand=True, settings=s)
        self.assertEqual(state, PlantState.BOOST)
        self.assertFalse(changed)
        # Nach 16 Minuten darf er aus
        state, changed, _ = m.update(now=16 * 60, feed_in_w=500, data_ok=True, demand=True, settings=s)
        self.assertEqual(state, PlantState.NORMAL)
        self.assertTrue(changed)

    def test_min_pause_blocks_new_boost(self):
        m = Machine()
        s = Settings(feed_in_on_w=1800, feed_in_off_w=900, min_runtime_min=0, min_pause_min=10)
        m.update(now=0, feed_in_w=2000, data_ok=True, demand=True, settings=s)
        m.update(now=10, feed_in_w=100, data_ok=True, demand=True, settings=s)  # aus bei t=10
        # Sofort wieder Überschuss -> Pause blockiert
        state, _changed, _ = m.update(now=20, feed_in_w=3000, data_ok=True, demand=True, settings=s)
        self.assertEqual(state, PlantState.NORMAL)
        # Nach der Pause erlaubt
        state, _changed, _ = m.update(now=10 + 10 * 60 + 1, feed_in_w=3000, data_ok=True, demand=True, settings=s)
        self.assertEqual(state, PlantState.BOOST)

    def test_bad_data_forces_normal(self):
        m = Machine(state=PlantState.BOOST, since=0)
        state, changed, _ = m.update(now=10, feed_in_w=None, data_ok=False, demand=True, settings=Settings())
        self.assertEqual(state, PlantState.NORMAL)
        self.assertTrue(changed)

    def test_holiday_forces_normal(self):
        m = Machine(state=PlantState.BOOST, since=0)
        s = Settings(holiday=True)
        state, _, _ = m.update(now=10, feed_in_w=5000, data_ok=True, demand=True, settings=s)
        self.assertEqual(state, PlantState.NORMAL)

    def test_no_demand_blocks_boost(self):
        m = Machine()
        state, _changed, _ = m.update(now=0, feed_in_w=5000, data_ok=True, demand=False, settings=Settings())
        self.assertEqual(state, PlantState.NORMAL)


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
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 60})], self.ctx(mode=Mode.SHADOW)
        )
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_blocks_on_emergency(self):
        acts, reasons = gate(
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 60})],
            self.ctx(mode=Mode.ACTIVE, emergency=True),
        )
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_blocks_stale(self):
        acts, reasons = gate(
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 60})],
            self.ctx(mode=Mode.ACTIVE, age=999),
        )
        self.assertEqual(acts, [])
        self.assertTrue(reasons)

    def test_gate_clamps_value(self):
        acts, reasons = gate(
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 99})], self.ctx(mode=Mode.ACTIVE)
        )
        self.assertFalse(reasons)
        self.assertEqual(acts[0].data["temperature"], 60)

    def test_gate_allows_safe_action(self):
        acts, reasons = gate(
            [Action("water_heater.x", "water_heater.set_temperature", {"temperature": 60})], self.ctx(mode=Mode.ACTIVE)
        )
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


class TestPlanner(unittest.TestCase):
    def test_active_mode_produces_action_on_boost(self):
        m = Machine()
        s = Settings(mode=Mode.ACTIVE, feed_in_on_w=1800, ww_boost_temp=60)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500),
            storage=r(50),
            grid_import=None,
            now=0,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
        )
        self.assertEqual(d.state, PlantState.BOOST)
        self.assertEqual(len(d.actions), 1)
        self.assertEqual(d.actions[0].data["temperature"], 60)

    def test_shadow_mode_no_action(self):
        m = Machine()
        s = Settings(mode=Mode.SHADOW)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500),
            storage=r(50),
            grid_import=None,
            now=0,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
        )
        self.assertEqual(d.actions, [])
        self.assertTrue(d.blocked)

    def test_off_mode_no_action(self):
        m = Machine()
        s = Settings(mode=Mode.OFF)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500),
            storage=r(50),
            grid_import=None,
            now=0,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
        )
        self.assertEqual(d.actions, [])

    def test_stale_data_no_action(self):
        m = Machine()
        s = Settings(mode=Mode.ACTIVE)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500, age=9999),
            storage=r(50),
            grid_import=None,
            now=0,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
        )
        self.assertEqual(d.actions, [])

    def test_self_heal_when_device_drifted(self):
        """Bleibt im Boost, aber das Gerät steht falsch -> erneut schreiben."""
        m = Machine(state=PlantState.BOOST, since=0)
        s = Settings(mode=Mode.ACTIVE, ww_boost_temp=60)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500),
            storage=r(50),
            grid_import=None,
            now=10,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
            current_temp=52.0,
        )
        self.assertEqual(len(d.actions), 1)
        self.assertEqual(d.actions[0].data["temperature"], 60)

    def test_no_write_when_already_at_target(self):
        m = Machine(state=PlantState.BOOST, since=0)
        s = Settings(mode=Mode.ACTIVE, ww_boost_temp=60)
        d = evaluate(
            machine=m,
            settings=s,
            feed_in=r(2500),
            storage=r(50),
            grid_import=None,
            now=10,
            previous_feed_in=2400,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
            current_temp=60.0,
        )
        self.assertEqual(d.actions, [])

    def test_boost_returns_normal_when_storage_warm(self):
        m = Machine(state=PlantState.BOOST, since=0)
        s = Settings(mode=Mode.ACTIVE, ww_boost_temp=60, min_runtime_min=0)
        state, changed, _ = m.update(now=100, feed_in_w=5000, data_ok=True, demand=False, settings=s)
        self.assertEqual(state, PlantState.NORMAL)
        self.assertTrue(changed)


class TestWallboxModule(unittest.TestCase):
    def _eval(self, *, modules, feed, wallbox_on, mode=Mode.ACTIVE):
        m = Machine()
        s = Settings(mode=mode, wallbox_on_w=4200, wallbox_off_w=2000)
        return evaluate(
            machine=m,
            settings=s,
            feed_in=r(feed),
            storage=r(45),
            grid_import=None,
            now=0,
            previous_feed_in=feed - 100,
            device_min=10,
            device_max=60,
            ww_entity="water_heater.x",
            enabled_modules=modules,
            wallbox_entity="switch.wallbox",
            wallbox_on=wallbox_on,
        )

    def test_wallbox_off_when_module_disabled(self):
        d = self._eval(modules={"core", "thermal"}, feed=6000, wallbox_on=False)
        self.assertFalse(any(a.entity_id == "switch.wallbox" for a in d.actions))

    def test_wallbox_turns_on_with_surplus(self):
        d = self._eval(modules={"core", "thermal", "wallbox"}, feed=6000, wallbox_on=False)
        self.assertTrue(any(a.service == "switch.turn_on" for a in d.actions))

    def test_wallbox_turns_off_when_surplus_gone(self):
        d = self._eval(modules={"core", "thermal", "wallbox"}, feed=100, wallbox_on=True)
        self.assertTrue(any(a.service == "switch.turn_off" for a in d.actions))

    def test_wallbox_blocked_in_shadow_mode(self):
        d = self._eval(modules={"core", "thermal", "wallbox"}, feed=6000, wallbox_on=False, mode=Mode.SHADOW)
        self.assertEqual([a for a in d.actions if a.entity_id == "switch.wallbox"], [])
        self.assertTrue(d.blocked)

    def test_heating_module_advises_only(self):
        d = self._eval(modules={"core", "thermal", "heating"}, feed=6000, wallbox_on=False)
        self.assertFalse(any(a.entity_id == "switch.wallbox" for a in d.actions))
        self.assertTrue(any("Heizung" in t for _, t in d.steps))


if __name__ == "__main__":
    unittest.main()
