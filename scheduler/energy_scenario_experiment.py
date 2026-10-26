"""Scenario-based energy-aware placement experiment.

This is a modeled scenario, not a measurement of Alibaba server energy.

Assumptions:
- Fixed one-hour evaluation horizon.
- Active server power = idle power + dynamic power * mean(GPU, CPU utilization).
- Inactive servers are assumed powered down (zero power).
- GPU-memory feasibility is NOT verified because the supplied server sample
  does not provide GPU-memory capacity and request units have not been verified.
- Workload execution durations are not modeled; no completion-time claims.
"""

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

import trace_experiment as trace  # noqa: E402
from order_sensitivity import build_orders  # noqa: E402

OUTPUT_ROOT = ROOT / "results" / "energy_scenarios"

# Explicit illustrative parameters; vary these for sensitivity analysis.
IDLE_POWER_W = 1000.0
DYNAMIC_POWER_W = 1700.0
HORIZON_HOURS = 1.0
HYBRID_LOW_LOAD_RESOURCE_WEIGHT = 0.35
HYBRID_HIGH_LOAD_RESOURCE_WEIGHT = 0.75
HIGH_LOAD_THRESHOLD = 0.80
EPSILON = 1e-9


def utilization_after(pod, server):
    gpu, cpu = trace.projected_load(pod, server)
    return gpu, cpu


def server_power_w(server, gpu_used=None, cpu_used=None):
    """Illustrative server power; inactive servers are assumed powered off."""
    gpu_used = server["gpu_used"] if gpu_used is None else gpu_used
    cpu_used = server["cpu_used"] if cpu_used is None else cpu_used

    if gpu_used <= EPSILON and cpu_used <= EPSILON:
        return 0.0

    gpu_util = gpu_used / server["gpu_capacity"]
    cpu_util = cpu_used / server["cpu_capacity"]
    mean_util = (gpu_util + cpu_util) / 2.0

    return IDLE_POWER_W + DYNAMIC_POWER_W * mean_util


def incremental_energy_wh(pod, server):
    """Incremental modeled energy over the fixed evaluation horizon."""
    before = server_power_w(server)
    after = server_power_w(
        server,
        gpu_used=server["gpu_used"] + pod["gpu_request_num"],
        cpu_used=server["cpu_used"] + pod["cpu_request_num"],
    )
    return max(0.0, after - before) * HORIZON_HOURS


def resource_score(pod, server):
    gpu_after, cpu_after = utilization_after(pod, server)
    return 1.0 - max(gpu_after, cpu_after)


def choose_energy_server(pod, candidates):
    """Lowest incremental modeled energy; server ID breaks ties."""
    return min(
        candidates,
        key=lambda s: (
            incremental_energy_wh(pod, s),
            s["server_id"],
        ),
    )


def choose_hardware_state_server(pod, candidates):
    """Balance projected GPU and CPU utilization using simulated state."""
    def score(server):
        gpu_after, cpu_after = utilization_after(pod, server)
        # Lower squared utilization penalizes heavily loaded resources.
        return (
            gpu_after ** 2 + cpu_after ** 2,
            max(gpu_after, cpu_after),
            server["server_id"],
        )

    return min(candidates, key=score)


def choose_shortlist_energy_server(pod, candidates, k):
    """Rank by projected resource balance, then minimize modeled energy."""
    if not candidates:
        raise ValueError("candidates must not be empty")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k must be a positive integer")

    ranked = sorted(
        candidates,
        key=lambda s: (
            max(utilization_after(pod, s)),
            sum(utilization_after(pod, s)),
            s["server_id"],
        ),
    )
    shortlist = ranked[:min(k, len(ranked))]
    return choose_energy_server(pod, shortlist), shortlist


def choose_hybrid_server(pod, candidates):
    """Adaptive resource/energy scoring with deterministic tie-breaking."""
    energy = {
        s["server_id"]: incremental_energy_wh(pod, s)
        for s in candidates
    }
    low = min(energy.values())
    high = max(energy.values())

    chosen_scores = {}
    for server in candidates:
        energy_value = energy[server["server_id"]]
        if math.isclose(high, low, abs_tol=EPSILON):
            energy_fit = 1.0
        else:
            energy_fit = (high - energy_value) / (high - low)

        projected_max = max(utilization_after(pod, server))
        alpha = (
            HYBRID_HIGH_LOAD_RESOURCE_WEIGHT
            if projected_max >= HIGH_LOAD_THRESHOLD
            else HYBRID_LOW_LOAD_RESOURCE_WEIGHT
        )
        combined = (
            alpha * resource_score(pod, server)
            + (1.0 - alpha) * energy_fit
        )
        chosen_scores[server["server_id"]] = (
            combined, alpha, energy_value
        )

    return min(
        candidates,
        key=lambda s: (
            -chosen_scores[s["server_id"]][0],
            s["server_id"],
        ),
    ), chosen_scores


def classify_pending(pod, inventory):
    """Explain why no GPU/CPU-feasible server was found.

    This diagnostic does not classify GPU-memory feasibility.
    """
    matching = [
        s for s in inventory
        if s["gpu_spec_public"] == pod["gpu_spec_public"]
    ]
    if not matching:
        return "no_matching_gpu_type"

    gpu_possible = [
        s for s in matching
        if s["gpu_capacity"] - s["gpu_used"]
        >= pod["gpu_request_num"] - EPSILON
    ]
    if gpu_possible and not any(
        s["cpu_capacity"] - s["cpu_used"]
        >= pod["cpu_request_num"] - EPSILON
        for s in gpu_possible
    ):
        return "cpu_capacity"

    if not gpu_possible:
        # Aggregate free GPU capacity can exist but be fragmented among
        # servers, none of which can satisfy this individual request.
        free_gpu = sum(
            max(0.0, s["gpu_capacity"] - s["gpu_used"])
            for s in matching
        )
        if free_gpu >= pod["gpu_request_num"] - EPSILON:
            return "gpu_fragmentation"
        return "gpu_capacity"

    return "gpu_cpu_combination"


def run_policy(policy, pods, servers, order_name):
    inventory = trace.fresh_inventory(servers)
    assignments = []

    for pod in pods:
        candidates = [s for s in inventory if trace.fits(pod, s)]
        row = {
            "policy": policy,
            "order": order_name,
            "pod_id": pod["pod_id"],
            "gpu_type": pod["gpu_spec_public"],
            "status": "pending",
            "server_id": "",
            "pending_reason": "",
            "incremental_energy_wh": "",
            "resource_weight": "",
            "memory_feasibility": "unverified",
        }

        if not candidates:
            row["pending_reason"] = classify_pending(pod, inventory)
            assignments.append(row)
            continue

        if policy == "workload_first_fit":
            # Workload-only baseline: first feasible server in inventory order.
            server = candidates[0]
            delta = incremental_energy_wh(pod, server)
            alpha = ""
        elif policy == "hardware_state_aware":
            # Uses projected simulator state, not live hardware telemetry.
            server = choose_hardware_state_server(pod, candidates)
            delta = incremental_energy_wh(pod, server)
            alpha = ""
        elif policy == "resource_aware":
            server = trace.choose_server("resource_aware", pod, candidates)
            delta = incremental_energy_wh(pod, server)
            alpha = 1.0
        elif policy == "energy_aware":
            server = choose_energy_server(pod, candidates)
            delta = incremental_energy_wh(pod, server)
            alpha = 0.0
        elif policy in {"shortlist_k2", "shortlist_k5", "shortlist_k10"}:
            k = int(policy.removeprefix("shortlist_k"))
            server, _shortlist = choose_shortlist_energy_server(
                pod, candidates, k
            )
            delta = incremental_energy_wh(pod, server)
            alpha = ""
        elif policy == "hybrid_adaptive":
            server, scores = choose_hybrid_server(pod, candidates)
            _, alpha, delta = scores[server["server_id"]]
        else:
            raise ValueError(f"Unknown policy: {policy}")

        server["gpu_used"] += pod["gpu_request_num"]
        server["cpu_used"] += pod["cpu_request_num"]

        row.update({
            "status": "placed",
            "server_id": server["server_id"],
            "incremental_energy_wh": round(delta, 6),
            "resource_weight": round(alpha, 4) if alpha != "" else "",
        })
        assignments.append(row)

    placed = sum(a["status"] == "placed" for a in assignments)
    pending = len(assignments) - placed
    active_servers = [
        s for s in inventory
        if s["gpu_used"] > EPSILON or s["cpu_used"] > EPSILON
    ]

    # Recompute the final state power, rather than summing incremental
    # placement deltas, to keep the energy accounting definition explicit.
    total_power_w = sum(server_power_w(s) for s in inventory)
    total_energy_wh = total_power_w * HORIZON_HOURS

    gpu_capacity = sum(s["gpu_capacity"] for s in inventory)
    gpu_used = sum(s["gpu_used"] for s in inventory)
    cpu_capacity = sum(s["cpu_capacity"] for s in inventory)
    cpu_used = sum(s["cpu_used"] for s in inventory)

    summary = {
        "policy": policy,
        "order": order_name,
        "pod_count": len(pods),
        "placed_pods": placed,
        "pending_pods": pending,
        "placement_rate_percent": round(100 * placed / len(pods), 4),
        "active_servers": len(active_servers),
        "aggregate_gpu_utilization_percent": round(
            100 * gpu_used / gpu_capacity, 4
        ),
        "aggregate_cpu_utilization_percent": round(
            100 * cpu_used / cpu_capacity, 4
        ),
        "modeled_power_w": round(total_power_w, 4),
        "modeled_energy_wh": round(total_energy_wh, 4),
        "energy_metric_definition": (
            "Final-state modeled active-server power summed across inventory "
            "times fixed horizon; not the sum of placement deltas"
        ),
        "energy_wh_per_placed_pod": (
            round(total_energy_wh / placed, 6) if placed else ""
        ),
        "horizon_hours": HORIZON_HOURS,
        "idle_power_w_per_active_server": IDLE_POWER_W,
        "dynamic_power_w_per_server": DYNAMIC_POWER_W,
        "inactive_server_assumption": "powered_off",
        "gpu_memory_feasibility": "UNVERIFIED",
        "completion_time": "NOT_MODELED",
        "energy_interpretation": (
            "Illustrative fixed-horizon scenario; not measured energy"
        ),
    }
    return assignments, summary


def write_rows(path, rows):
    if not rows:
        raise ValueError(f"Refusing to write empty result: {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    pods, servers = trace.load_inputs()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    all_assignments = []
    all_summaries = []

    for order_name, _seed, ordered_pods in build_orders(pods):
        for policy in (
            "workload_first_fit",
            "hardware_state_aware",
            "resource_aware",
            "energy_aware",
            "shortlist_k2",
            "shortlist_k5",
            "shortlist_k10",
            "hybrid_adaptive",
        ):
            assignments, summary = run_policy(
                policy, ordered_pods, servers, order_name
            )
            all_assignments.extend(assignments)
            all_summaries.append(summary)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    assignment_path = OUTPUT_ROOT / f"assignments_{stamp}.csv"
    summary_path = OUTPUT_ROOT / f"summary_{stamp}.csv"
    write_rows(assignment_path, all_assignments)
    write_rows(summary_path, all_summaries)

    print("EAWSK energy scenario experiment")
    print("================================")
    print(f"Workloads per order: {len(pods)}")
    print(f"Servers: {len(servers)}")
    print("Orders: original, largest_gpu_first, random seeds 11/23/42/87")
    print("Policies include workload first-fit and simulated hardware-state-aware")
    print("GPU/CPU feasibility: enforced before scoring")
    print("GPU-memory feasibility: UNVERIFIED; no server capacity field")
    print(f"Power scenario: idle={IDLE_POWER_W} W, dynamic={DYNAMIC_POWER_W} W")
    print(f"Horizon: {HORIZON_HOURS} hour(s)")
    print("Inactive servers assumed powered off.")
    print("Execution durations and completion time: not modeled.")
    print("Energy values are scenario estimates, not measured energy.\n")

    for s in all_summaries:
        print(
            f"{s['order']:18s} {s['policy']:18s} "
            f"placed={s['placed_pods']:4d} "
            f"pending={s['pending_pods']:4d} "
            f"energy_Wh={s['modeled_energy_wh']:10.2f} "
            f"Wh/placed={s['energy_wh_per_placed_pod']}"
        )

    print(f"\nAssignments: {assignment_path}")
    print(f"Summary:     {summary_path}")


if __name__ == "__main__":
    main()
