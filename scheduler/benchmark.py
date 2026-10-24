import csv
import sys
from datetime import datetime
from pathlib import Path
from feasibility import eligible_nodes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

from policy import score_node

OUTPUT_DIR = ROOT / "results" / "reports"

# Illustrative simulation inputs, not measured node power values.
SCENARIOS = [
    {
        "scenario": "scenario_01",
        "nodes": [
            {"name": "node-a", "cpu_percent": 75, "energy_watts": 65, "feasible": True},
            {"name": "node-b", "cpu_percent": 35, "energy_watts": 30, "feasible": True},
            {"name": "node-c", "cpu_percent": 50, "energy_watts": 40, "feasible": True},
        ],
    },
    {
        "scenario": "scenario_02",
        "nodes": [
            {"name": "node-a", "cpu_percent": 20, "energy_watts": 25, "feasible": False},
            {"name": "node-b", "cpu_percent": 65, "energy_watts": 45, "feasible": True},
            {"name": "node-c", "cpu_percent": 40, "energy_watts": 35, "feasible": True},
        ],
    },
    {
        "scenario": "scenario_03",
        "nodes": [
            {"name": "node-a", "cpu_percent": 30, "energy_watts": 30, "feasible": True},
            {"name": "node-b", "cpu_percent": 80, "energy_watts": 70, "feasible": False},
            {"name": "node-c", "cpu_percent": 45, "energy_watts": 25, "feasible": True},
        ],
    },
    {
        "scenario": "scenario_04",
        "nodes": [
            {"name": "node-a", "cpu_percent": 60, "energy_watts": 35, "feasible": True},
            {"name": "node-b", "cpu_percent": 25, "energy_watts": 55, "feasible": True},
            {"name": "node-c", "cpu_percent": 40, "energy_watts": 30, "feasible": False},
        ],
    },
    {
        "scenario": "scenario_05",
        "nodes": [
            {"name": "node-a", "cpu_percent": 90, "energy_watts": 80, "feasible": False},
            {"name": "node-b", "cpu_percent": 55, "energy_watts": 40, "feasible": True},
            {"name": "node-c", "cpu_percent": 35, "energy_watts": 50, "feasible": True},
        ],
    },
    {
        "scenario": "scenario_06",
        "nodes": [
            {"name": "node-a", "cpu_percent": 70, "energy_watts": 60, "feasible": True},
            {"name": "node-b", "cpu_percent": 45, "energy_watts": 35, "feasible": True},
            {"name": "node-c", "cpu_percent": 20, "energy_watts": 20, "feasible": False},
        ],
    },
]


def select_nodes(scenario):
    feasible = [n for n in scenario["nodes"] if n["feasible"]]
    if not feasible:
        raise ValueError(f"{scenario['scenario']} has no feasible nodes")

    # Baseline: first feasible node in candidate order.
    default_node = feasible[0]

    # Proposed policy: lowest normalized CPU/power score among feasible nodes.
    energy_node = min(
        feasible,
        key=lambda n: score_node(n["cpu_percent"], n["energy_watts"]),
    )
    return feasible, default_node, energy_node

def select_nodes_by_resources(
    scenario,
    pod_cpu_request,
    pod_memory_request,
):
    """Select nodes using CPU/memory feasibility before ranking."""
    candidates = scenario["nodes"]

    feasible = eligible_nodes(
        candidates,
        pod_cpu_request,
        pod_memory_request,
    )

    if not feasible:
        raise ValueError(
            f"{scenario['scenario']} has no resource-feasible nodes"
        )

    # Baseline: first resource-feasible node in candidate order.
    baseline_node = feasible[0]

    # Proposed policy: lowest score among resource-feasible nodes.
    energy_node = min(
        feasible,
        key=lambda node: score_node(
            node["cpu_percent"],
            node["energy_watts"],
        ),
    )

    return feasible, baseline_node, energy_node

def run_benchmark():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"scheduler_benchmark_{stamp}.csv"
    records = []
    improvements = []
    energy_wins = 0

    for scenario in SCENARIOS:
        feasible, default_node, energy_node = select_nodes(scenario)
        best_score = score_node(
            energy_node["cpu_percent"], energy_node["energy_watts"]
        )
        default_score = score_node(
            default_node["cpu_percent"], default_node["energy_watts"]
        )
        gap = default_score - best_score
        improvements.append(gap)
        if energy_node["name"] != default_node["name"]:
            energy_wins += 1

        for policy_name, node in (
            ("first_feasible_baseline", default_node),
            ("energy_aware", energy_node),
        ):
            node_score = score_node(node["cpu_percent"], node["energy_watts"])
            records.append({
                "scenario": scenario["scenario"],
                "policy": policy_name,
                "selected_node": node["name"],
                "feasible_node_count": len(feasible),
                "cpu_percent": node["cpu_percent"],
                "illustrative_power_watts": node["energy_watts"],
                "score": round(node_score, 6),
                "best_feasible_score": round(best_score, 6),
                "score_gap_from_best": round(node_score - best_score, 6),
                "is_lowest_score_feasible_node": node_score == best_score,
            })

        print(
            f"{scenario['scenario']}: "
            f"baseline={default_node['name']} (score {default_score:.3f}); "
            f"energy-aware={energy_node['name']} (score {best_score:.3f})"
        )

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    print("\nSimulation summary")
    print("------------------")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Energy-aware chose a different node in {energy_wins}/{len(SCENARIOS)} scenarios")
    print(f"Mean baseline score gap from best feasible score: {sum(improvements) / len(improvements):.4f}")
    print("The energy-aware policy selects a lowest-score feasible node in every scenario.")
    print("Scores and power inputs are illustrative; this is not a real cluster energy test.")
    print(f"CSV saved to: {output_path}")


def run_resource_benchmark():
    """Run a separate benchmark with CPU and memory feasibility checks."""
    import csv
    from datetime import datetime
    from pathlib import Path

    result_rows = []
    scenarios = [
        {
            "scenario": "resource_01",
            "pod_cpu_request": 0.5,
            "pod_memory_request": 512 * 1024**2,
            "nodes": [
                {
                    "name": "node-too-small",
                    "allocatable_cpu": 2.0,
                    "requested_cpu": 1.9,
                    "allocatable_memory": 4 * 1024**3,
                    "requested_memory": 3 * 1024**3,
                    "cpu_percent": 5,
                    "energy_watts": 5,
                },
                {
                    "name": "node-a",
                    "allocatable_cpu": 4.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 8 * 1024**3,
                    "requested_memory": 2 * 1024**3,
                    "cpu_percent": 60,
                    "energy_watts": 70,
                },
                {
                    "name": "node-b",
                    "allocatable_cpu": 8.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 16 * 1024**3,
                    "requested_memory": 2 * 1024**3,
                    "cpu_percent": 25,
                    "energy_watts": 30,
                },
            ],
        },
        {
            "scenario": "resource_02",
            "pod_cpu_request": 1.0,
            "pod_memory_request": 1024 * 1024**2,
            "nodes": [
                {
                    "name": "node-c",
                    "allocatable_cpu": 2.0,
                    "requested_cpu": 0.5,
                    "allocatable_memory": 4 * 1024**3,
                    "requested_memory": 1 * 1024**3,
                    "cpu_percent": 35,
                    "energy_watts": 45,
                },
                {
                    "name": "node-d",
                    "allocatable_cpu": 4.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 8 * 1024**3,
                    "requested_memory": 2 * 1024**3,
                    "cpu_percent": 50,
                    "energy_watts": 60,
                },
            ],
        },
        {
            "scenario": "resource_03",
            "pod_cpu_request": 1.5,
            "pod_memory_request": 2 * 1024**3,
            "nodes": [
                {
                    "name": "node-e",
                    "allocatable_cpu": 2.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 8 * 1024**3,
                    "requested_memory": 5 * 1024**3,
                    "cpu_percent": 20,
                    "energy_watts": 25,
                },
                {
                    "name": "node-f",
                    "allocatable_cpu": 4.0,
                    "requested_cpu": 1.0,
                    "allocatable_memory": 16 * 1024**3,
                    "requested_memory": 4 * 1024**3,
                    "cpu_percent": 40,
                    "energy_watts": 50,
                },
            ],
        },
    ]

    print("\nResource-based benchmark")
    print("------------------------")

    for scenario in scenarios:
        eligible, baseline, energy_aware = select_nodes_by_resources(
            scenario,
            scenario["pod_cpu_request"],
            scenario["pod_memory_request"],
        )
        print(f'{scenario["scenario"]}:')
        print(f'  Eligible nodes: {", ".join(n["name"] for n in eligible)}')
        print(f'  Baseline: {baseline["name"]}')
        print(f'  Energy-aware: {energy_aware["name"]}')
        result_rows.append({
            "scenario": scenario["scenario"],
            "pod_cpu_request_cores": scenario["pod_cpu_request"],
            "pod_memory_request_bytes": scenario["pod_memory_request"],
            "eligible_nodes": ",".join(n["name"] for n in eligible),
            "baseline_node": baseline["name"],
            "energy_aware_node": energy_aware["name"],
            "baseline_score": round(
                score_node(
                    baseline["cpu_percent"],
                    baseline["energy_watts"],
                ), 4
            ),
            "energy_aware_score": round(
                score_node(
                    energy_aware["cpu_percent"],
                    energy_aware["energy_watts"],
                ), 4
            ),
            "power_data": "synthetic",
        })

    report_dir = Path("results/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"resource_benchmark_{timestamp}.csv"

    with report_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=result_rows[0].keys())
        writer.writeheader()
        writer.writerows(result_rows)

    print(f"Resource benchmark CSV saved to: {report_path.resolve()}")

    print(
        "\nResource and power values are synthetic; "
        "this is not a real cluster energy test."
    )

if __name__ == "__main__":
    run_benchmark()
    run_resource_benchmark()
