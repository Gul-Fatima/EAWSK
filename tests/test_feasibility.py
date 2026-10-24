import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scheduler"),
)

from feasibility import node_fits_pod, eligible_nodes


class TestNodeFeasibility(unittest.TestCase):
    def setUp(self):
        self.node_a = {
            "name": "node-a",
            "allocatable_cpu": 4.0,
            "requested_cpu": 2.0,
            "allocatable_memory": 8 * 1024**3,
            "requested_memory": 4 * 1024**3,
        }

    def test_node_fits_when_cpu_and_memory_are_available(self):
        self.assertTrue(
            node_fits_pod(self.node_a, 1.0, 1024**3)
        )

    def test_rejects_insufficient_cpu(self):
        self.assertFalse(
            node_fits_pod(self.node_a, 2.1, 1024**3)
        )

    def test_rejects_insufficient_memory(self):
        self.assertFalse(
            node_fits_pod(self.node_a, 1.0, 5 * 1024**3)
        )

    def test_rejects_when_both_resources_are_insufficient(self):
        self.assertFalse(
            node_fits_pod(self.node_a, 3.0, 5 * 1024**3)
        )

    def test_rejects_negative_pod_requests(self):
        with self.assertRaises(ValueError):
            node_fits_pod(self.node_a, -0.1, 1024)

    def test_eligible_nodes_filters_infeasible_candidates(self):
        node_b = {
            "name": "node-b",
            "allocatable_cpu": 8.0,
            "requested_cpu": 1.0,
            "allocatable_memory": 16 * 1024**3,
            "requested_memory": 2 * 1024**3,
        }

        result = eligible_nodes(
            [self.node_a, node_b],
            pod_cpu_request=2.1,
            pod_memory_request=3 * 1024**3,
        )

        self.assertEqual([node["name"] for node in result], ["node-b"])


if __name__ == "__main__":
    unittest.main()
