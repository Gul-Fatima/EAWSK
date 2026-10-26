"""Trace-driven placement experiment using sampled Alibaba GPU data.

Energy is not calculated in this first version. The experiment establishes
consistent GPU/CPU feasibility and comparable placement results first.
The pod CSV is a stratified random sample, not a chronological replay.
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

POD_FILE = ROOT / "data/sample/alibaba_pods_sample_2000.csv"
SERVER_FILE = ROOT / "data/sample/alibaba_servers_sample.csv"
OUTPUT_DIR = ROOT / "results/reports"


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def number(row, key):
    value = row.get(key, "")
    if value is None or str(value).strip() == "":
        return 0.0
    result = float(value)
    if result < 0:
        raise ValueError(f"Negative value in {key}: {result}")
    return result


def load_inputs():
    pods = load_csv(POD_FILE)
    servers = load_csv(SERVER_FILE)

    if not pods or not servers:
        raise ValueError("Pod and server datasets must both contain rows")

    required_pod = {
        "pod_id", "gpu_spec_public", "gpu_request", "cpu_request_cores"
    }
    required_server = {
        "server_id", "gpu_spec_public", "gpu_count", "cpu_capacity_cores"
    }

    if not required_pod.issubset(pods[0]):
        raise ValueError(f"Pod CSV missing: {required_pod - set(pods[0])}")
    if not required_server.issubset(servers[0]):
        raise ValueError(
            f"Server CSV missing: {required_server - set(servers[0])}"
        )

    for pod in pods:
        pod["gpu_request_num"] = number(pod, "gpu_request")
        pod["cpu_request_num"] = number(pod, "cpu_request_cores")
        if pod["gpu_request_num"] <= 0:
            raise ValueError(f"Non-positive GPU request for {pod['pod_id']}")

    for server in servers:
        server["gpu_capacity"] = number(server, "gpu_count")
        server["cpu_capacity"] = number(server, "cpu_capacity_cores")
        if server["gpu_capacity"] <= 0 or server["cpu_capacity"] <= 0:
            raise ValueError(f"Invalid capacity for {server['server_id']}")

    # Stable ordering makes repeated runs reproducible.
    # This preserves the sample's file order; it does NOT imply arrival time.
    return pods, servers


def fresh_inventory(servers):
    inventory = []
    for server in servers:
        inventory.append({
            **server,
            "gpu_used": 0.0,
            "cpu_used": 0.0,
        })
    return inventory


def fits(pod, server):
    return (
        pod["gpu_spec_public"] == server["gpu_spec_public"]
        and server["gpu_capacity"] - server["gpu_used"]
            >= pod["gpu_request_num"] - 1e-9
        and server["cpu_capacity"] - server["cpu_used"]
            >= pod["cpu_request_num"] - 1e-9
    )


def projected_load(pod, server):
    gpu_after = (
        server["gpu_used"] + pod["gpu_request_num"]
    ) / server["gpu_capacity"]
    cpu_after = (
        server["cpu_used"] + pod["cpu_request_num"]
    ) / server["cpu_capacity"]
    return gpu_after, cpu_after


def choose_server(policy, pod, candidates):
    if policy == "first_fit":
        return candidates[0]

    if policy == "resource_aware":
        # Prefer the server with the lowest projected maximum utilization.
        # This spreads load rather than packing it.
        return min(
            candidates,
            key=lambda s: (
                max(projected_load(pod, s)),
                sum(projected_load(pod, s)),
                s["server_id"],
            ),
        )

    if policy == "energy_aware":
        # Preliminary heuristic only: prefer packing requests onto servers
        # that are already more utilized, reducing the number of partially
        # used servers. This is NOT a power or energy measurement/model.
        return min(
            candidates,
            key=lambda s: (
                -(
                    s["gpu_used"] / s["gpu_capacity"]
                    + s["cpu_used"] / s["cpu_capacity"]
                ),
                s["server_id"],
            ),
        )

    raise ValueError(f"Unknown policy: {policy}")


def run_policy(policy, pods, servers):
    inventory = fresh_inventory(servers)
    assignments = []

    for pod in pods:
        candidates = [s for s in inventory if fits(pod, s)]

        if not candidates:
            assignments.append({
                "policy": policy,
                "pod_id": pod["pod_id"],
                "gpu_type": pod["gpu_spec_public"],
                "gpu_request": pod["gpu_request_num"],
                "cpu_request_cores": pod["cpu_request_num"],
                "status": "pending",
                "server_id": "",
            })
            continue

        server = choose_server(policy, pod, candidates)
        server["gpu_used"] += pod["gpu_request_num"]
        server["cpu_used"] += pod["cpu_request_num"]

        assignments.append({
            "policy": policy,
            "pod_id": pod["pod_id"],
            "gpu_type": pod["gpu_spec_public"],
            "gpu_request": pod["gpu_request_num"],
            "cpu_request_cores": pod["cpu_request_num"],
            "status": "placed",
            "server_id": server["server_id"],
        })

    placed = sum(a["status"] == "placed" for a in assignments)
    pending = len(assignments) - placed
    gpu_capacity = sum(s["gpu_capacity"] for s in inventory)
    gpu_used = sum(s["gpu_used"] for s in inventory)
    cpu_capacity = sum(s["cpu_capacity"] for s in inventory)
    cpu_used = sum(s["cpu_used"] for s in inventory)

    # GPU utilization is only an aggregate across this mixed-GPU inventory.
    # It does not imply different GPU models are interchangeable.
    summary = {
        "policy": policy,
        "pod_count": len(pods),
        "placed_pods": placed,
        "pending_pods": pending,
        "placement_rate_percent": round(100 * placed / len(pods), 4),
        "aggregate_gpu_request": round(gpu_used, 4),
        "aggregate_gpu_capacity": round(gpu_capacity, 4),
        "gpu_capacity_utilization_percent": round(
            100 * gpu_used / gpu_capacity, 4
        ),
        "cpu_request_cores_placed": round(cpu_used, 4),
        "cpu_capacity_cores": round(cpu_capacity, 4),
        "cpu_capacity_utilization_percent": round(
            100 * cpu_used / cpu_capacity, 4
        ),
        "energy_wh": "",
        "energy_saving_percent": "",
        "energy_note": "Not modeled in this experiment version",
    }

    return assignments, summary


def main():
    pods, servers = load_inputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    policies = ["first_fit", "resource_aware", "energy_aware"]
    all_assignments = []
    summaries = []

    for policy in policies:
        assignments, summary = run_policy(policy, pods, servers)
        all_assignments.extend(assignments)
        summaries.append(summary)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    assignment_path = OUTPUT_DIR / f"trace_assignments_{stamp}.csv"
    summary_path = OUTPUT_DIR / f"trace_summary_{stamp}.csv"

    with assignment_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_assignments[0].keys())
        writer.writeheader()
        writer.writerows(all_assignments)

    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summaries[0].keys())
        writer.writeheader()
        writer.writerows(summaries)

    print("EAWSK trace-driven placement experiment")
    print("======================================")
    print(f"Pods: {len(pods)}")
    print(f"Servers: {len(servers)}")
    print("Input order: sampled CSV order; not chronological")
    print("Feasibility: exact GPU type, GPU quantity, CPU request")
    print("GPU-memory feasibility: not applied; units still require verification")
    print("Energy: NOT modeled; no energy-saving claim is produced")
    print()

    for result in summaries:
        print(
            f"{result['policy']:16s} "
            f"placed={result['placed_pods']:4d} "
            f"pending={result['pending_pods']:4d} "
            f"placement_rate={result['placement_rate_percent']:7.2f}% "
            f"GPU_util={result['gpu_capacity_utilization_percent']:7.2f}% "
            f"CPU_util={result['cpu_capacity_utilization_percent']:7.2f}%"
        )

    print(f"\nAssignments: {assignment_path}")
    print(f"Summary:     {summary_path}")


if __name__ == "__main__":
    main()
