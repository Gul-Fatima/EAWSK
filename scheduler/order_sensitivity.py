"""Evaluate placement and illustrative-proxy sensitivity to pod ordering.

The workload is a sampled batch, not a chronological trace replay.
The energy metric is a dimensionless illustrative proxy, not measured energy.
"""

import csv
import random
from datetime import datetime, timezone
from pathlib import Path

from trace_experiment import load_inputs, OUTPUT_DIR
from paper_inspired_experiment import ALPHAS, run_policy

BASELINE_POLICIES = ["first_fit", "resource_aware", "energy_aware"]
RANDOM_SEEDS = [11, 23, 42, 87]


def build_orders(pods):
    orders = [("original", None, list(pods))]

    largest_first = sorted(
        pods,
        key=lambda p: (
            -p["gpu_request_num"],
            -p["cpu_request_num"],
            p["pod_id"],
        ),
    )
    orders.append(("largest_gpu_first", None, largest_first))

    for seed in RANDOM_SEEDS:
        shuffled = list(pods)
        random.Random(seed).shuffle(shuffled)
        orders.append((f"random_seed_{seed}", seed, shuffled))

    return orders


def main():
    pods, servers = load_inputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    orders = build_orders(pods)
    all_summaries = []

    for order_name, seed, ordered_pods in orders:
        # Baselines and paper-inspired variants use the same evaluation
        # implementation, inventory, feasibility rules, and pod order.
        for policy in BASELINE_POLICIES:
            _, summary = run_policy(policy, ordered_pods, servers)
            summary["order_name"] = order_name
            summary["random_seed"] = "" if seed is None else seed
            summary["input_order_note"] = (
                "Sampled batch ordering; not chronological"
            )
            all_summaries.append(summary)

        for alpha in ALPHAS:
            policy_name = f"paper_inspired_alpha_{alpha:.2f}"
            _, summary = run_policy(
                "paper_inspired", ordered_pods, servers, alpha=alpha
            )
            summary["policy"] = policy_name
            summary["order_name"] = order_name
            summary["random_seed"] = "" if seed is None else seed
            summary["input_order_note"] = (
                "Sampled batch ordering; not chronological"
            )
            all_summaries.append(summary)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = OUTPUT_DIR / f"order_sensitivity_{stamp}.csv"

    fieldnames = [
        "order_name",
        "random_seed",
        "input_order_note",
        "policy",
        "alpha_resource_weight",
        "alpha_energy_proxy_weight",
        "pod_count",
        "placed_pods",
        "pending_pods",
        "placement_rate_percent",
        "aggregate_gpu_request",
        "aggregate_gpu_capacity",
        "gpu_capacity_utilization_percent",
        "cpu_request_cores_placed",
        "cpu_capacity_cores",
        "cpu_capacity_utilization_percent",
        "active_servers",
        "final_normalized_power_proxy",
        "energy_wh",
        "energy_saving_percent",
        "energy_note",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_summaries)

    print("EAWSK policy and pod-order sensitivity experiment")
    print("================================================")
    print(f"Pods: {len(pods)}")
    print(f"Servers: {len(servers)}")
    print(f"Orders: {len(orders)}")
    print(f"Policies per order: {len(BASELINE_POLICIES) + len(ALPHAS)}")
    print(f"Runs: {len(all_summaries)}")
    print("Input: sampled batch; not chronological")
    print("Energy: dimensionless illustrative proxy only; not measured")
    print()

    print(
        f"{'Order':<20} {'Policy':<27} {'Placed':>7} "
        f"{'Pending':>8} {'Rate':>8} {'Active':>7} {'Proxy':>11}"
    )
    print("-" * 94)

    for row in all_summaries:
        print(
            f"{row['order_name']:<20} {row['policy']:<27} "
            f"{row['placed_pods']:>7} {row['pending_pods']:>8} "
            f"{row['placement_rate_percent']:>7.2f}% "
            f"{row['active_servers']:>7} "
            f"{row['final_normalized_power_proxy']:>11.4f}"
        )

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
