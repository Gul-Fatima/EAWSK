import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

from benchmark import select_nodes,select_nodes_by_resources


class TestSchedulerBenchmark(unittest.TestCase):
    def test_infeasible_low_score_node_is_never_selected(self):
        scenario = {
            "scenario": "test",
            "nodes": [
                {"name": "unavailable", "cpu_percent": 5,
                 "energy_watts": 5, "feasible": False},
                {"name": "eligible", "cpu_percent": 50,
                 "energy_watts": 40, "feasible": True},
                {"name": "better", "cpu_percent": 30,
                 "energy_watts": 25, "feasible": True},
            ],
        }
        feasible, baseline, energy_aware = select_nodes(scenario)
        self.assertEqual(baseline["name"], "eligible")
        self.assertEqual(energy_aware["name"], "better")
        self.assertNotIn("unavailable", [n["name"] for n in feasible])

    def test_no_feasible_nodes_raises_error(self):
        scenario = {
            "scenario": "none",
            "nodes": [
                {"name": "node-a", "cpu_percent": 10,
                 "energy_watts": 10, "feasible": False},
            ],
        }
        with self.assertRaises(ValueError):
            select_nodes(scenario)
    def test_resource_feasibility_excludes_low_score_node(self):
        scenario = {
            "scenario": "resource-test",
            "nodes": [
                {
                    "name": "too-small",
                    "cpu_percent": 5,
                    "energy_watts": 5,
                    "allocatable_cpu": 2.0,
                    "requested_cpu": 1.9,
                    "allocatable_memory": 4 * 1024**3,
                    "requested_memory": 3 * 1024**3,
                },
                {
                    "name": "eligible-a",
                    "cpu_percent": 50,
                    "energy_watts": 40,
                    "allocatable_cpu": 4.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 8 * 1024**3,
                    "requested_memory": 2 * 1024**3,
                },
                {
                    "name": "eligible-b",
                    "cpu_percent": 30,
                    "energy_watts": 25,
                    "allocatable_cpu": 4.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 8 * 1024**3,
                    "requested_memory": 2 * 1024**3,
                },
            ],
        }

        feasible, baseline, energy_aware = select_nodes_by_resources(
            scenario,
            pod_cpu_request=0.5,
            pod_memory_request=512 * 1024**2,
        )

        self.assertEqual(
            [node["name"] for node in feasible],
            ["eligible-a", "eligible-b"],
        )
        self.assertEqual(baseline["name"], "eligible-a")
        self.assertEqual(energy_aware["name"], "eligible-b")

    def test_resource_selection_raises_when_no_node_fits(self):
        scenario = {
            "scenario": "no-resource-fit",
            "nodes": [
                {
                    "name": "too-small",
                    "cpu_percent": 5,
                    "energy_watts": 5,
                    "allocatable_cpu": 1.0,
                    "requested_cpu": 0.9,
                    "allocatable_memory": 1024**3,
                    "requested_memory": 900 * 1024**2,
                },
            ],
        }

        with self.assertRaises(ValueError):
            select_nodes_by_resources(
                scenario,
                pod_cpu_request=0.5,
                pod_memory_request=512 * 1024**2,
            )

if __name__ == "__main__":
    unittest.main()
