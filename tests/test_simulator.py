import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

from simulate import default_style_choice, energy_aware_choice


class TestSimulator(unittest.TestCase):

    def setUp(self):
        self.nodes = [
            {"name": "node-a", "cpu_percent": 75, "energy_watts": 65},
            {"name": "node-b", "cpu_percent": 35, "energy_watts": 30},
            {"name": "node-c", "cpu_percent": 50, "energy_watts": 40},
        ]

    def test_default_style_uses_first_node(self):
        self.assertEqual(default_style_choice(self.nodes)["name"], "node-a")

    def test_energy_aware_selects_lowest_score(self):
        self.assertEqual(energy_aware_choice(self.nodes)["name"], "node-b")


if __name__ == "__main__":
    unittest.main()
