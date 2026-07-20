import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "backend" / "d6" / "automation" / "rule_catalog.json"


class AutomationCatalogTests(unittest.TestCase):
    def test_catalog_has_exactly_100_unique_rules(self):
        from backend.d6.automation.rule_schema import load_catalog
        rules = load_catalog(CATALOG)
        self.assertEqual(len(rules), 100)
        self.assertEqual(len({rule["id"] for rule in rules}), 100)

    def test_catalog_has_twenty_core_and_eighty_unlockable_rules(self):
        from backend.d6.automation.rule_schema import load_catalog
        rules = load_catalog(CATALOG)
        self.assertEqual(sum(rule["tier"] == "core" for rule in rules), 20)
        self.assertEqual(sum(rule["tier"] == "unlockable" for rule in rules), 80)

    def test_catalog_rejects_any_automatic_door_action(self):
        from backend.d6.automation.rule_schema import validate_rule
        errors = validate_rule(
            {"id": "X", "tier": "core", "actions": [{"deviceId": "door_01", "action": "open"}]},
            {"door_01"}, set(),
        )
        self.assertTrue(any("door" in error.lower() for error in errors))

    def test_catalog_contains_requested_rules(self):
        from backend.d6.automation.rule_schema import load_catalog
        rules = {rule["id"]: rule for rule in load_catalog(CATALOG)}
        self.assertEqual(rules["A001"]["actions"][0]["deviceId"], "ac_01")
        self.assertEqual(rules["A001"]["actions"][0]["action"], "dry")
        self.assertEqual(rules["A006"]["actions"][0]["deviceId"], "curtain_01")
        self.assertEqual(rules["A008"]["actions"][0]["deviceId"], "light_01")
        self.assertEqual(rules["A011"]["actions"][0]["action"], "auto")


if __name__ == "__main__":
    unittest.main()
