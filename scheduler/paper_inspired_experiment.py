"""Paper-inspired resource/energy placement experiment for EAWSK.

Adaptation, not an exact reproduction of the paper:
- Feasibility filtering reuses trace_experiment.py.
- Resource score rewards balanced projected GPU/CPU utilization.
- Energy score uses a normalized illustrative power proxy.
- No Wh or measured energy savings are claimed.

The Alibaba sample is not chronological and contains no measured node power
or task execution durations. Therefore, this is a placement-policy experiment,
not a real energy-consumption benchmark.
"""

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scheduler"))

import trace_experiment as trace  # noqa: E402

OUTPUT_DIR = ROOT / "results/reports"

# alpha is the resource-fit weight; 1-alpha is the energy-proxy weight.
ALPHAS = (0.0, 0.25, 0.50, 0.75, 1.0)

# Illustrative normalized power proxy, NOT hardware watts:
# proxy = idle component for a non-empty server
#       + dynamic component proportional to mean GPU/CPU utilization.
# These constants are dimensionless and must not be reported as Wh or W.
IDLE_PROXY = 0.5
DYNAMIC_PROXY = 0.5


def utilization(pod, server):
    gpu_after, cpu_after = trace.projected_load(pod, server)
    return gpu_after, cpu_after


def normalized_power_proxy(server, gpu_used=None, cpu_used=None):
    """Dimensionless proxy; not a measured or hardware-calibrated power model."""
    gpu_used = server["gpu_used"] if gpu_used is None else gpu_used
    cpu_used = server["cpu_used"] if cpu_used is None else cpu_used

    if gpu_used <= 1e-12 and cpu_used <= 1e-12:
        return 0.0

    gpu_util = gpu_used / server["gpu_capacity"]
    cpu_util = cpu_used / server["cpu_capacity"]
    mean_util = (gpu_util + cpu_util) / 2.0

    return IDLE_PROXY + DYNAMIC_PROXY * mean_util


def projected_proxy_increment(pod, server):
    """Increment in the dimensionless proxy caused by this placement."""
    before = normalized_power_proxy(server)
    after = normalized_power_proxy(
        server,
        gpu_used=server["gpu_used"] + pod["gpu_request_num"],
        cpu_used=server["cpu_used"] + pod["cpu_request_num"],
    )
    return max(0.0, after - before)


def candidate_scores(pod, candidates):
    """Return resource scores and relative energy-proxy scores per candidate."""
    deltas = {
        s["server_id"]: projected_proxy_increment(pod, s)
        for s in candidates
    }
    low = min(deltas.values())
    high = max(deltas.values())

    scores = {}
    for server in candidates:
        gpu_after, cpu_after = utilization(pod, server)

        # Higher is better: favor balanced projected resource utilization.
        resource_score = 1.0 - max(gpu_after, cpu_after)

        # Higher is better: favor a smaller incremental proxy cost.
        if math.isclose(high, low, rel_tol=1e-12, abs_tol=1e-12):
            energy_score = 1.0
        else:
            energy_score = (high - deltas[server["server_id"]]) / (high - low)

        scores[server["server_id"]] = {
            "resource_score": resource_score,
            "energy_score": energy_score,
            "proxy_increment": deltas[server["server_id"]],
        }

    return scores


def choose_paper_inspired_server(pod, candidates, alpha):
    """Choose a feasible server using explicit, reproducible policy semantics."""
    if not candidates:
        raise ValueError("At least one feasible candidate is required.")
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0.0 and 1.0.")

    # Endpoint 1: exactly reuse the existing resource-aware policy.
    # This prevents the energy proxy from affecting alpha=1.
    if math.isclose(alpha, 1.0, abs_tol=1e-12):
        return trace.choose_server("resource_aware", pod, candidates)

    scores = candidate_scores(pod, candidates)

    # Endpoint 2: minimize the illustrative proxy increment only.
    # Server ID provides deterministic tie-breaking.
    if math.isclose(alpha, 0.0, abs_tol=1e-12):
        return min(
            candidates,
            key=lambda server: (
                scores[server["server_id"]]["proxy_increment"],
                server["server_id"],
            ),
        )

    # Intermediate settings combine resource and proxy scores.
    # Ties use server ID only, rather than silently favoring either component.
    return min(
        candidates,
        key=lambda server: (
            -(
                alpha * scores[server["server_id"]]["resource_score"]
                + (1.0 - alpha)
                * scores[server["server_id"]]["energy_score"]
            ),
            server["server_id"],
        ),
    )


def run_policy(policy, pods, servers, alpha=None):
    inventory = trace.fresh_inventory(servers)
    assignments = []

    for pod in pods:
        candidates = [s for s in inventory if trace.fits(pod, s)]

        row = {
            "policy": policy,
            "alpha_resource_weight": "" if alpha is None else alpha,
            "pod_id": pod["pod_id"],
            "gpu_type": pod["gpu_spec_public"],
            "gpu_request": pod["gpu_request_num"],
            "cpu_request_cores": pod["cpu_request_num"],
            "status": "pending",
            "server_id": "",
            "resource_score": "",
            "energy_proxy_score": "",
            "incremental_power_proxy": "",
        }

        if not candidates:
            assignments.append(row)
            continue

        if policy == "paper_inspired":
            scores = candidate_scores(pod, candidates)
            server = choose_paper_inspired_server(pod, candidates, alpha)
            selected = scores[server["server_id"]]
            row["resource_score"] = round(selected["resource_score"], 6)
            row["energy_proxy_score"] = round(selected["energy_score"], 6)
            row["incremental_power_proxy"] = round(
                selected["proxy_increment"], 6
            )
        else:
            server = trace.choose_server(policy, pod, candidates)

        server["gpu_used"] += pod["gpu_request_num"]
        server["cpu_used"] += pod["cpu_request_num"]

        row["status"] = "placed"
        row["server_id"] = server["server_id"]
        assignments.append(row)

    placed = sum(a["status"] == "placed" for a in assignments)
    pending = len(assignments) - placed

    gpu_capacity = sum(s["gpu_capacity"] for s in inventory)
    gpu_used = sum(s["gpu_used"] for s in inventory)
    cpu_capacity = sum(s["cpu_capacity"] for s in inventory)
    cpu_used = sum(s["cpu_used"] for s in inventory)
    proxy_total = sum(normalized_power_proxy(s) for s in inventory)
    active_servers = sum(
        s["gpu_used"] > 1e-12 or s["cpu_used"] > 1e-12 for s in inventory
    )

    summary = {
        "policy": policy,
        "alpha_resource_weight": "" if alpha is None else alpha,
        "alpha_energy_proxy_weight": "" if alpha is None else round(1-alpha, 4),
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
        "active_servers": active_servers,
        "final_normalized_power_proxy": round(proxy_total, 6),
        "energy_wh": "",
        "energy_saving_percent": "",
        "energy_note": (
            "Dimensionless illustrative proxy only; not measured power or Wh. "
            "No execution durations; do not claim energy savings."
        ),
    }

    return assignments, summary


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No rows to write to {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    pods, servers = trace.load_inputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_assignments = []
    summaries = []

    # Comparable baselines use the same input order and feasibility rules.
    for policy in ("first_fit", "resource_aware", "energy_aware"):
        assignments, summary = run_policy(policy, pods, servers)
        all_assignments.extend(assignments)
        summaries.append(summary)

    # Weight sensitivity: alpha=0 is proxy-only; alpha=1 is resource-only.
    for alpha in ALPHAS:
        policy = f"paper_inspired_alpha_{alpha:.2f}"
        assignments, summary = run_policy(
            "paper_inspired", pods, servers, alpha=alpha
        )
        # Use the readable policy label in saved rows.
        for row in assignments:
            row["policy"] = policy
        summary["policy"] = policy
        all_assignments.extend(assignments)
        summaries.append(summary)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    assignment_path = OUTPUT_DIR / f"paper_inspired_assignments_{stamp}.csv"
    summary_path = OUTPUT_DIR / f"paper_inspired_summary_{stamp}.csv"

    write_csv(assignment_path, all_assignments)
    write_csv(summary_path, summaries)

    print("EAWSK paper-inspired scheduling experiment")
    print("==========================================")
    print(f"Pods: {len(pods)}")
    print(f"Servers: {len(servers)}")
    print("Input order: sampled CSV order; not chronological")
    print("Feasibility: exact GPU type, GPU quantity, CPU request")
    print("GPU memory: not checked; units require verification")
    print("Energy: dimensionless illustrative proxy only; not measured")
    print(f"Assignment report: {assignment_path}")
    print(f"Summary report:    {summary_path}")
    print()
    for row in summaries:
        print(
            f"{row['policy']:28s} "
            f"placed={row['placed_pods']:4d} "
            f"pending={row['pending_pods']:4d} "
            f"rate={row['placement_rate_percent']:7.2f}% "
            f"active_servers={row['active_servers']:3d} "
            f"proxy={row['final_normalized_power_proxy']:.4f}"
        )


if __name__ == "__main__":
    main()
