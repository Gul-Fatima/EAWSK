import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scheduler"),
)

from policy import score_node, rank_nodes


class TestEnergyAwarePolicy(unittest.TestCase):

    def test_lower_score_is_better(self):
        low = score_node(cpu_percent=20, energy_watts=30)
        high = score_node(cpu_percent=80, energy_watts=60)
        self.assertLess(low, high)

    def test_nodes_are_ranked_lowest_score_first(self):
        nodes = [
            {"name": "node-a", "cpu_percent": 80, "energy_watts": 60},
            {"name": "node-b", "cpu_percent": 20, "energy_watts": 30},
        ]

        ranked = rank_nodes(nodes)

        self.assertEqual(ranked[0]["name"], "node-b")
        self.assertEqual(ranked[1]["name"], "node-a")

    def test_invalid_cpu_is_rejected(self):
        with self.assertRaises(ValueError):
            score_node(cpu_percent=120, energy_watts=30)

    def test_negative_power_is_rejected(self):
        with self.assertRaises(ValueError):
            score_node(cpu_percent=20, energy_watts=-1)

    def test_power_above_maximum_is_capped(self):
        score = score_node(
            cpu_percent=0,
            energy_watts=200,
            max_power_watts=100,
        )
        self.assertAlmostEqual(score, 0.4)

    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            score_node(
                cpu_percent=50,
                energy_watts=30,
                cpu_weight=0.5,
                energy_weight=0.2,
            )

    def test_negative_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            score_node(
                cpu_percent=50,
                energy_watts=30,
                cpu_weight=-0.1,
                energy_weight=1.1,
            )

if __name__ == "__main__":
    unittest.main()
