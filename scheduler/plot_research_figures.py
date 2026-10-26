"""Generate reproducible figures from saved EAWSK experiment CSVs."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "results" / "energy_scenarios"
REPORT_DIR = ROOT / "results" / "research_reports"
FIGURE_DIR = SCENARIO_DIR / "figures"


def latest_file(directory, pattern):
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No files matching {pattern!r} in {directory}"
        )
    return matches[-1]


def save_figure(fig, stem):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_DIR / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURE_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {stem}.png and {stem}.pdf")


def figure1_placement_rates():
    path = latest_file(SCENARIO_DIR, "summary_*.csv")
    df = pd.read_csv(path)

    order_names = [
        "original", "largest_gpu_first", "random_seed_11",
        "random_seed_23", "random_seed_42", "random_seed_87",
    ]
    df["order"] = pd.Categorical(
        df["order"], categories=order_names, ordered=True
    )
    pivot = df.pivot(
        index="order", columns="policy", values="placement_rate_percent"
    ).sort_index()

    ax = pivot.plot(kind="bar", figsize=(11, 6))
    ax.set_title("Placement rate by policy and workload ordering")
    ax.set_xlabel("Workload ordering")
    ax.set_ylabel("Placed workloads (%)")
    ax.legend(title="Policy")
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="x", rotation=25)
    save_figure(ax.figure, "figure1_placement_rate_by_order")


def figure2_pending_by_gpu_and_reason():
    path = latest_file(SCENARIO_DIR, "assignments_*.csv")
    df = pd.read_csv(path)
    df = df[
        (df["status"] == "pending")
        & (df["policy"] == "resource_aware")
    ].copy()

    if df.empty:
        raise ValueError("No pending resource-aware assignments found.")

    counts = (
        df.groupby(["gpu_type", "pending_reason"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )

    ax = counts.plot(
        kind="barh", stacked=True, figsize=(10, 7), width=0.8
    )
    ax.set_title(
        "Pending workloads by GPU type and reason "
        "(resource-aware policy)"
    )
    ax.set_xlabel("Pending workload count")
    ax.set_ylabel("GPU type")
    ax.legend(title="Pending reason", bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.grid(axis="x", alpha=0.3)
    save_figure(ax.figure, "figure2_pending_by_gpu_type_and_reason")


def figure3_alpha_sweep():
    run_dirs = sorted(p for p in REPORT_DIR.glob("run_*") if p.is_dir())
    if not run_dirs:
        raise FileNotFoundError(f"No report runs found in {REPORT_DIR}")

    summary_path = run_dirs[-1] / "experiment_summary.csv"
    df = pd.read_csv(summary_path)

    df = df[
        df["policy"].astype(str).str.startswith("paper_inspired_alpha_")
    ].copy()
    if df.empty:
        raise ValueError(
            f"No paper_inspired_alpha_* rows in {summary_path}"
        )

    df["alpha"] = pd.to_numeric(df["alpha_resource_weight"], errors="coerce")
    df["placement_rate_percent"] = pd.to_numeric(
        df["placement_rate_percent"], errors="coerce"
    )
    grouped = (
        df.groupby("alpha")["placement_rate_percent"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .sort_values("alpha")
    )
    errors = grouped["std"].fillna(0)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        grouped["alpha"], grouped["mean"], yerr=errors,
        marker="o", capsize=4
    )
    ax.set_title(
        "Placement rate versus resource weight "
        "(existing dimensionless-proxy experiment)"
    )
    ax.set_xlabel("Resource weight, alpha")
    ax.set_ylabel("Mean placement rate across workload orders (%)")
    ax.set_xticks(sorted(grouped["alpha"].tolist()))
    ax.grid(True, alpha=0.3)
    save_figure(fig, "figure3_placement_rate_vs_alpha")


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure1_placement_rates()
    figure2_pending_by_gpu_and_reason()
    figure3_alpha_sweep()
    print(f"\nFigures directory: {FIGURE_DIR}")


if __name__ == "__main__":
    main()
