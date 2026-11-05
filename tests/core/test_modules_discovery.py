"""Tests für Store-Registry, Abhängigkeiten und Geräteerkennung."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_PARENT = Path(__file__).resolve().parents[2] / "custom_components" / "solarflow"
sys.path.insert(0, str(CORE_PARENT))

from core.discovery import EntityInfo, suggest
from core.modules import (
    CORE_MODULE_ID,
    MODULE_SPECS,
    MODULES_BY_ID,
    default_enabled_modules,
    dependents_of,
    resolve_dependencies,
    store_cards,
)


class TestModuleRegistry(unittest.TestCase):
    def test_core_present_and_mandatory(self):
        self.assertIn(CORE_MODULE_ID, MODULES_BY_ID)
        self.assertFalse(MODULES_BY_ID[CORE_MODULE_ID].optional)
        self.assertTrue(MODULES_BY_ID[CORE_MODULE_ID].default_enabled)

    def test_all_specs_have_unique_ids(self):
        ids = [s.module_id for s in MODULE_SPECS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_dependencies_resolve_transitively(self):
        # heating hängt an thermal, thermal an core
        result = resolve_dependencies(set(), module_id="heating")
        self.assertEqual(result, {"core", "thermal", "heating"})

    def test_store_cards_shape(self):
        cards = store_cards({"core", "thermal"})
        by_id = {c["module_id"]: c for c in cards}
        self.assertTrue(by_id["core"]["enabled"])
        self.assertTrue(by_id["thermal"]["enabled"])
        self.assertFalse(by_id["wallbox"]["enabled"])
        self.assertIn("name_de", by_id["core"])
        self.assertIn("name_en", by_id["core"])

    def test_dependents(self):
        deps = dependents_of("thermal", {"core", "thermal", "heating"})
        self.assertIn("heating", deps)

    def test_default_enabled_is_core_only(self):
        self.assertEqual(default_enabled_modules(), {"core"})


class TestDiscovery(unittest.TestCase):
    def test_suggests_feed_in(self):
        entities = [
            EntityInfo("sensor.solarnet_leistung_netzeinspeisung", "sensor", "Netzeinspeisung"),
            EntityInfo("sensor.pv_leistung", "sensor", "PV Leistung"),
            EntityInfo("water_heater.vitocal_ww", "water_heater", "Warmwasser"),
        ]
        sug = {s.role: s for s in suggest(entities)}
        self.assertEqual(sug["feed_in"].entity_id, "sensor.solarnet_leistung_netzeinspeisung")
        self.assertGreater(sug["feed_in"].confidence, 0)
        self.assertEqual(sug["ww_water_heater"].entity_id, "water_heater.vitocal_ww")

    def test_no_entities_no_crash(self):
        sug = suggest([])
        self.assertTrue(all(s.entity_id is None for s in sug))


if __name__ == "__main__":
    unittest.main()
