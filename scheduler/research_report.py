"""Generate reproducible, paper-oriented reports for EAWSK experiments.

All scheduling results are simulated from the supplied trace sample and
server inventory. The normalized power proxy is dimensionless, not measured
energy. This script does not modify existing experiment outputs.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd

from order_sensitivity import build_orders
from trace_experiment import load_inputs, fresh_inventory, fits
from paper_inspired_experiment import ALPHAS, run_policy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "results" / "research_reports"
BASELINES = ("first_fit", "resource_aware", "energy_aware")

SUMMARY_METRICS = [
    "placed_pods",
    "pending_pods",
    "placement_rate_percent",
    "aggregate_gpu_request",
    "gpu_capacity_utilization_percent",
    "cpu_request_cores_placed",
    "cpu_capacity_utilization_percent",
    "active_servers",
    "final_normalized_power_proxy",
]


def markdown_table(frame):
    """Render a DataFrame as a Markdown table without optional packages."""
    frame = frame.copy().fillna("")
    columns = [str(c) for c in frame.columns]

    def cell(value):
        text = str(value).replace("|", r"\\|")
        return text.replace("\\n", " ").replace("\\r", " ")

    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for values in frame.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(cell(v) for v in values) + " |")
    return "\\n".join(rows)


def configuration_list():
    configs = [
        {"configuration": p, "policy": p, "alpha": None}
        for p in BASELINES
    ]
    configs.extend(
        {
            "configuration": f"paper_inspired_alpha_{a:.2f}",
            "policy": "paper_inspired",
            "alpha": a,
        }
        for a in ALPHAS
    )
    return configs


def pending_reason(assignment, inventory, pod):
    """Classify why a pending pod cannot fit at its decision point."""
    compatible = [
        s for s in inventory
        if s["gpu_spec_public"] == pod["gpu_spec_public"]
    ]
    gpu_fit = [
        s for s in compatible
        if s["gpu_capacity"] - s["gpu_used"]
        >= pod["gpu_request_num"] - 1e-9
    ]
    cpu_fit = [
        s for s in compatible
        if s["cpu_capacity"] - s["cpu_used"]
        >= pod["cpu_request_num"] - 1e-9
    ]

    if not gpu_fit and not cpu_fit:
        return "no_gpu_fit_and_no_cpu_fit"
    if not gpu_fit:
        return "gpu_capacity"
    if not cpu_fit:
        return "cpu_capacity"
    return "gpu_cpu_fragmentation"


def diagnose_from_assignments(ordered_pods, servers, assignments):
    """Replay the saved decisions to label each pending pod's blocking reason."""
    inventory = fresh_inventory(servers)
    reason_by_index = {}

    if len(ordered_pods) != len(assignments):
        raise AssertionError("Assignment count differs from ordered pod count")

    for i, (pod, assignment) in enumerate(zip(ordered_pods, assignments)):
        if str(pod["pod_id"]) != str(assignment["pod_id"]):
            raise AssertionError(
                f"Assignment order mismatch at index {i}: "
                f"{pod['pod_id']} vs {assignment['pod_id']}"
            )

        if assignment["status"] == "placed":
            sid = str(assignment["server_id"])
            server = next(
                (s for s in inventory if str(s["server_id"]) == sid), None
            )
            if server is None:
                raise AssertionError(f"Unknown assigned server: {sid}")
            if not fits(pod, server):
                raise AssertionError(
                    f"Saved assignment no longer fits during replay: "
                    f"pod={pod['pod_id']} server={sid}"
                )
            server["gpu_used"] += pod["gpu_request_num"]
            server["cpu_used"] += pod["cpu_request_num"]
            reason_by_index[i] = ""
        else:
            reason_by_index[i] = pending_reason(
                assignment, inventory, pod
            )

    return reason_by_index


def make_type_summary(assignments, pods, servers, order_name, config_name):
    a = pd.DataFrame(assignments)
    p = pd.DataFrame(pods)
    s = pd.DataFrame(servers)

    placed = a[a["status"] == "placed"]
    placed_by_type = placed.groupby("gpu_type").agg(
        placed_pods=("pod_id", "count"),
        gpu_units_placed=("gpu_request", "sum"),
        cpu_cores_placed=("cpu_request_cores", "sum"),
    )
    total_by_type = p.groupby("gpu_spec_public").agg(
        total_pods=("pod_id", "count"),
        requested_gpu_all_pods=("gpu_request_num", "sum"),
        requested_cpu_all_pods=("cpu_request_num", "sum"),
    )
    capacity_by_type = s.groupby("gpu_spec_public").agg(
        servers=("server_id", "count"),
        gpu_capacity=("gpu_capacity", "sum"),
        cpu_capacity_cores=("cpu_capacity", "sum"),
    )

    result = total_by_type.join(
        placed_by_type, how="left"
    ).join(capacity_by_type, how="left").fillna(0)

    result["pending_pods"] = result["total_pods"] - result["placed_pods"]
    result["gpu_capacity_utilization_percent"] = (
        100 * result["gpu_units_placed"]
        / result["gpu_capacity"].replace(0, float("nan"))
    )
    result["cpu_capacity_utilization_percent"] = (
        100 * result["cpu_cores_placed"]
        / result["cpu_capacity_cores"].replace(0, float("nan"))
    )
    result["order"] = order_name
    result["configuration"] = config_name
    result.index.name = "gpu_type"
    return result.reset_index()


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = OUTPUT_ROOT / f"run_{timestamp}"
    outdir.mkdir(parents=True, exist_ok=False)

    pods, servers = load_inputs()
    order_entries = build_orders(pods)
    orders = {
        name: ordered
        for name, _, ordered in order_entries
    }
    configs = configuration_list()

    all_assignments = []
    all_summaries = []
    all_pending = []
    all_pending_reason_summaries = []
    all_type_summaries = []
    validation_rows = []

    # Run all 8 configurations on all 6 deterministic orderings.
    for order_name, ordered_pods in orders.items():
        for config in configs:
            assignments, summary = run_policy(
                config["policy"],
                ordered_pods,
                servers,
                alpha=config["alpha"],
            )

            reason_by_index = diagnose_from_assignments(
                ordered_pods, servers, assignments
            )

            for i, assignment in enumerate(assignments):
                row = dict(assignment)
                row["order"] = order_name
                row["configuration"] = config["configuration"]
                row["pending_reason"] = reason_by_index[i]
                all_assignments.append(row)

                if row["status"] != "placed":
                    all_pending.append(row.copy())

            summary_row = dict(summary)
            summary_row["order"] = order_name
            summary_row["configuration"] = config["configuration"]
            summary_row["input_pod_count"] = len(ordered_pods)
            all_summaries.append(summary_row)

            # Pending reasons by GPU type for this order/configuration.
            pending_rows = [
                row for row in assignments
                if row["status"] != "placed"
            ]
            pending_frame = pd.DataFrame([
                {
                    "gpu_type": r["gpu_type"],
                    "pending_reason": reason_by_index[i],
                }
                for i, r in enumerate(assignments)
                if r["status"] != "placed"
            ])
            if len(pending_frame):
                reason_table = (
                    pending_frame.groupby(["gpu_type", "pending_reason"])
                    .size().rename("pending_pods").reset_index()
                )
            else:
                reason_table = pd.DataFrame(
                    columns=["gpu_type", "pending_reason", "pending_pods"]
                )
            reason_table["order"] = order_name
            reason_table["configuration"] = config["configuration"]
            all_pending_reason_summaries.extend(
                reason_table.to_dict("records")
            )

            all_type_summaries.append(
                make_type_summary(
                    assignments, ordered_pods, servers,
                    order_name, config["configuration"]
                )
            )

            validation_rows.append({
                "check": "pod_accounting",
                "order": order_name,
                "configuration": config["configuration"],
                "passed": (
                    len(assignments) == len(ordered_pods)
                    and summary["placed_pods"] + summary["pending_pods"]
                    == len(ordered_pods)
                ),
                "details": (
                    f"assignments={len(assignments)}, "
                    f"placed={summary['placed_pods']}, "
                    f"pending={summary['pending_pods']}"
                ),
            })

            validation_rows.append({
                "check": "unique_pod_ids",
                "order": order_name,
                "configuration": config["configuration"],
                "passed": (
                    len({str(r["pod_id"]) for r in assignments})
                    == len(ordered_pods)
                ),
                "details": "Every input pod should occur exactly once",
            })

    assignments_df = pd.DataFrame(all_assignments)
    summaries_df = pd.DataFrame(all_summaries)
    pending_df = pd.DataFrame(all_pending)
    reasons_df = pd.DataFrame(all_pending_reason_summaries)
    type_df = pd.concat(all_type_summaries, ignore_index=True)

    # Compare alpha=1 against resource-aware on the same order.
    for order_name in orders:
        ref = summaries_df[
            (summaries_df["order"] == order_name)
            & (summaries_df["configuration"] == "resource_aware")
        ].iloc[0]
        test = summaries_df[
            (summaries_df["order"] == order_name)
            & (summaries_df["configuration"] == "paper_inspired_alpha_1.00")
        ].iloc[0]

        for metric in SUMMARY_METRICS:
            left, right = float(ref[metric]), float(test[metric])
            passed = abs(left - right) <= 1e-5
            validation_rows.append({
                "check": "alpha_1_matches_resource_aware",
                "order": order_name,
                "configuration": "paper_inspired_alpha_1.00",
                "passed": passed,
                "details": (
                    f"{metric}: resource_aware={left}, alpha_1={right}"
                ),
            })

        ref_assignments = assignments_df[
            (assignments_df["order"] == order_name)
            & (assignments_df["configuration"] == "resource_aware")
        ].sort_values("pod_id").reset_index(drop=True)
        test_assignments = assignments_df[
            (assignments_df["order"] == order_name)
            & (assignments_df["configuration"] == "paper_inspired_alpha_1.00")
        ].sort_values("pod_id").reset_index(drop=True)

        same = (
            ref_assignments["status"].tolist()
            == test_assignments["status"].tolist()
            and ref_assignments["server_id"].fillna("").astype(str).tolist()
            == test_assignments["server_id"].fillna("").astype(str).tolist()
        )
        validation_rows.append({
            "check": "alpha_1_assignments_match_resource_aware",
            "order": order_name,
            "configuration": "paper_inspired_alpha_1.00",
            "passed": same,
            "details": "Per-pod status and assigned server comparison",
        })

    # Dataset profile: descriptive, not a claim of chronological arrivals.
    pod_df = pd.DataFrame(pods)
    server_df = pd.DataFrame(servers)

    dataset_profile = pd.DataFrame([
        {"metric": "sampled_pods", "value": len(pod_df)},
        {"metric": "sampled_servers", "value": len(server_df)},
        {"metric": "gpu_types_in_pods",
         "value": pod_df["gpu_spec_public"].nunique()},
        {"metric": "gpu_types_in_servers",
         "value": server_df["gpu_spec_public"].nunique()},
        {"metric": "unique_workload_ids",
         "value": pod_df["workload_id"].nunique()
         if "workload_id" in pod_df else ""},
        {"metric": "total_gpu_request_units",
         "value": pod_df["gpu_request_num"].sum()},
        {"metric": "total_cpu_request_cores",
         "value": pod_df["cpu_request_num"].sum()},
        {"metric": "gpu_memory_feasibility_checked", "value": False},
        {"metric": "chronological_order_verified", "value": False},
        {"metric": "energy_measured", "value": False},
    ])

    server_profile = server_df.groupby("gpu_spec_public").agg(
        server_count=("server_id", "count"),
        total_gpu_capacity=("gpu_capacity", "sum"),
        max_gpu_capacity_per_server=("gpu_capacity", "max"),
        total_cpu_capacity_cores=("cpu_capacity", "sum"),
        max_cpu_capacity_per_server=("cpu_capacity", "max"),
    ).reset_index().rename(columns={"gpu_spec_public": "gpu_type"})

    demand_profile = pod_df.groupby("gpu_spec_public").agg(
        pod_count=("pod_id", "count"),
        total_gpu_request=("gpu_request_num", "sum"),
        max_gpu_request=("gpu_request_num", "max"),
        total_cpu_request_cores=("cpu_request_num", "sum"),
        max_cpu_request_cores=("cpu_request_num", "max"),
    ).reset_index().rename(columns={"gpu_spec_public": "gpu_type"})

    capacity_pressure = demand_profile.merge(
        server_profile, on="gpu_type", how="outer"
    )
    capacity_pressure["gpu_demand_to_capacity_ratio"] = (
        capacity_pressure["total_gpu_request"]
        / capacity_pressure["total_gpu_capacity"].replace(0, float("nan"))
    )

    validation_df = pd.DataFrame(validation_rows)

    # Write machine-readable reports.
    files = {
        "experiment_summary.csv": summaries_df,
        "assignments_all.csv": assignments_df,
        "pending_pods_all.csv": pending_df,
        "pending_reasons_by_gpu_type.csv": reasons_df,
        "gpu_type_summary_all.csv": type_df,
        "dataset_profile.csv": dataset_profile,
        "server_inventory_profile.csv": server_profile,
        "gpu_demand_capacity_profile.csv": capacity_pressure,
        "validation_checks.csv": validation_df,
    }
    for filename, frame in files.items():
        frame.to_csv(outdir / filename, index=False)

    metadata = {
        "generated_utc": timestamp,
        "input_pods": len(pods),
        "input_servers": len(servers),
        "orders": list(orders.keys()),
        "baseline_policies": list(BASELINES),
        "paper_inspired_alpha_values": list(ALPHAS),
        "configuration_count": len(configs),
        "experiment_run_count": len(orders) * len(configs),
        "energy_is_measured": False,
        "energy_proxy_is_dimensionless": True,
        "gpu_memory_feasibility_checked": False,
        "chronological_arrival_order_verified": False,
        "random_order_seeds": [11, 23, 42, 87],
    }
    (outdir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    failed = validation_df[~validation_df["passed"].astype(bool)]
    best = summaries_df.sort_values(
        ["order", "placement_rate_percent"],
        ascending=[True, False],
    )

    report = [
        "# EAWSK Research Experiment Report",
        "",
        f"- Generated UTC: `{timestamp}`",
        f"- Input sample: {len(pods)} pods, {len(servers)} servers",
        f"- Experiment runs: {len(orders) * len(configs)}",
        "- Results are simulated scheduling outcomes, not live-cluster measurements.",
        "- The energy field is a dimensionless illustrative proxy, not watts, Wh, or measured energy.",
        "- GPU-memory feasibility is not checked by this experiment.",
        "- The original input order is not verified to be chronological.",
        "",
        "## Output files",
        "",
        "| File | Contents |",
        "|---|---|",
        "| `experiment_summary.csv` | One row per ordering/configuration |",
        "| `assignments_all.csv` | Per-pod placement, server, scores, proxy increment, pending reason |",
        "| `pending_pods_all.csv` | Pending pods only |",
        "| `pending_reasons_by_gpu_type.csv` | Pending reason counts by type/order/configuration |",
        "| `gpu_type_summary_all.csv` | Placed/pending pods, GPU and CPU use by type |",
        "| `dataset_profile.csv` | Sample-level descriptive profile |",
        "| `server_inventory_profile.csv` | Server capacity by GPU type |",
        "| `gpu_demand_capacity_profile.csv` | Per-type demand-to-capacity ratios |",
        "| `validation_checks.csv` | Accounting and alpha=1 regression checks |",
        "| `run_metadata.json` | Run configuration and explicit limitations |",
        "",
        "## Validation",
        "",
        f"- Checks performed: {len(validation_df)}",
        f"- Failed checks: {len(failed)}",
        "",
    ]

    if len(failed):
        report.extend([
            "The following checks failed and must be investigated before publication:",
            "",
            markdown_table(failed),
            "",
        ])
    else:
        report.append("All generated validation checks passed.")
        report.append("")

    report.extend([
        "## Highest placement rate per ordering",
        "",
        best.groupby("order", sort=False).head(1)[
            ["order", "configuration", "placed_pods",
             "pending_pods", "placement_rate_percent",
             "active_servers", "final_normalized_power_proxy"]
        ].pipe(markdown_table),
        "",
        "## Interpretation cautions",
        "",
        "1. Pod placement rate counts each pod equally, regardless of its GPU request.",
        "2. GPU/CPU utilization is based on requested resources allocated by the simulator, not observed runtime utilization.",
        "3. The proxy does not establish actual energy consumption or energy savings.",
        "4. The sample inventory is capacity-constrained for some GPU types; report per-type pressure.",
        "5. Pending-reason labels describe the immediate placement constraint at the scheduling decision point.",
        "6. These results do not establish statistical significance; random-order repetitions are sensitivity scenarios, not independent sampled datasets.",
        "",
    ])
    (outdir / "README.md").write_text(
        "\n".join(report), encoding="utf-8"
    )

    print(f"\nReport directory: {outdir}")
    print(f"Configurations: {len(configs)}")
    print(f"Orderings: {len(orders)}")
    print(f"Total experiment runs: {len(orders) * len(configs)}")
    print(f"Validation checks: {len(validation_df)}")
    print(f"Failed validation checks: {len(failed)}")
    print("\nGenerated files:")
    for path in sorted(outdir.iterdir()):
        print(f"  {path.name} ({path.stat().st_size:,} bytes)")

    if len(failed):
        print("\nFAILED VALIDATION CHECKS:")
        print(failed.to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
