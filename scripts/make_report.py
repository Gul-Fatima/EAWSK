import csv
import glob
import os
import statistics
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(ROOT, "results", "raw")
REPORT_DIR = os.path.join(ROOT, "results", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

FIELDS = [
    "source_file", "timestamp", "project_name", "duration",
    "energy_consumed", "cpu_energy", "ram_energy", "emissions",
    "cpu_utilization_percent", "ram_utilization_percent",
    "cpu_model", "tracking_mode",
]

def read_energy_files():
    rows = []
    for path in sorted(glob.glob(os.path.join(SOURCE_DIR, "*.csv"))):
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or "energy_consumed" not in reader.fieldnames:
                    continue
                for row in reader:
                    rows.append({
                        "source_file": os.path.basename(path),
                        **{key: row.get(key, "") for key in FIELDS
                           if key != "source_file"},
                    })
        except (OSError, csv.Error) as exc:
            print(f"Skipping {path}: {exc}")
    return rows

def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def find_one(pattern):
    matches = glob.glob(os.path.join(SOURCE_DIR, pattern))
    return matches[0] if len(matches) == 1 else None

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def fmt(value, digits=9):
    return f"{value:.{digits}f}"

def controlled_run(label):
    energy_path = find_one(f"energy_{label}_*.csv")
    if not energy_path:
        return None

    energy_rows = read_csv(energy_path)
    if not energy_rows:
        return None

    e = energy_rows[0]
    energy = number(e.get("energy_consumed"))
    duration = number(e.get("duration"))
    if energy is None:
        return None

    resource_name = os.path.basename(energy_path).replace(
        "energy_", "resource_metrics_", 1
    )
    resource_path = os.path.join(SOURCE_DIR, resource_name)
    if not os.path.isfile(resource_path):
        return {
            "label": label, "energy": energy, "duration": duration,
            "node_cpu": None, "node_memory": None,
            "pod_samples": 0, "pod_cpu": None,
        }

    metric_rows = read_csv(resource_path)
    node_rows = [
        r for r in metric_rows
        if r.get("metric_type") == "node" and r.get("status") == "ok"
    ]
    pod_rows = [
        r for r in metric_rows
        if r.get("metric_type") == "pod"
        and r.get("status") == "ok"
        and r.get("resource_name", "").startswith("cpu-test-")
    ]

    def average(rows, key):
        values = [number(r.get(key)) for r in rows]
        values = [v for v in values if v is not None]
        return statistics.mean(values) if values else None

    return {
        "label": label,
        "energy": energy,
        "duration": duration,
        "node_cpu": average(node_rows, "cpu_percent"),
        "node_memory": average(node_rows, "memory_percent"),
        "pod_samples": len(pod_rows),
        "pod_cpu": average(pod_rows, "cpu_cores"),
    }

def write_table(f, headers, rows):
    f.write("| " + " | ".join(headers) + " |\n")
    f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
    for row in rows:
        f.write("| " + " | ".join(str(v) for v in row) + " |\n")
    f.write("\n")

all_rows = read_energy_files()

# Preserve the original all-energy-record export.
csv_path = os.path.join(REPORT_DIR, "energy_summary.csv")
with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(all_rows)

# Main paired comparison uses the complete repeat for pair 3.
baseline_labels = ["baseline_01", "baseline_02", "baseline_03"]
loaded_labels = ["loaded_01", "loaded_02", "loaded_03_repeat"]
baselines = [controlled_run(label) for label in baseline_labels]
loadeds = [controlled_run(label) for label in loaded_labels]
pairs = []
for i, (b, l) in enumerate(zip(baselines, loadeds), start=1):
    if not b or not l or b["energy"] <= 0:
        continue
    pairs.append({
        "pair": i,
        "baseline": b,
        "loaded": l,
        "change_pct": (l["energy"] / b["energy"] - 1) * 100,
    })

# Read the most recent scheduler simulation CSV.
benchmark_files = sorted(
    glob.glob(os.path.join(REPORT_DIR, "scheduler_benchmark_*.csv"))
)
benchmark_rows = read_csv(benchmark_files[-1]) if benchmark_files else []
benchmark_scenarios = {}
for row in benchmark_rows:
    benchmark_scenarios.setdefault(row.get("scenario", ""), {})[
        row.get("policy", "")
    ] = row

md_path = os.path.join(REPORT_DIR, "energy_summary.md")
with open(md_path, "w") as f:
    f.write("# Energy-Aware Kubernetes Scheduling: Experiment Summary\n\n")
    f.write(f"Report generated: {datetime.now().astimezone().isoformat(timespec='seconds')}\n\n")
    f.write(f"Historical and experiment energy records found: {len(all_rows)}.\n\n")

    f.write("## 1. Historical CodeCarbon records\n\n")
    f.write(
        "The table below retains all energy records discovered in `results/raw`. "
        "These records include older exploratory runs and newer controlled runs; "
        "they should not all be treated as one homogeneous experiment.\n\n"
    )
    historical_rows = []
    for r in all_rows:
        historical_rows.append([
            r["source_file"],
            r["duration"] or "N/A",
            r["energy_consumed"] or "N/A",
            r["cpu_utilization_percent"] or "N/A",
            r["tracking_mode"] or "N/A",
        ])
    write_table(
        f,
        ["Source file", "Duration (s)", "Energy (kWh)", "CPU util. (%)", "Tracking mode"],
        historical_rows,
    )

    f.write("## 2. Controlled CPU workload experiment\n\n")
    f.write(
        "Pair 1 compares `baseline_01` with `loaded_01`; pair 2 compares "
        "`baseline_02` with `loaded_02`; pair 3 compares `baseline_03` with "
        "`loaded_03_repeat`. The original `loaded_03` is excluded from paired "
        "analysis because it had incomplete CPU-test pod sampling, but its raw "
        "files are preserved.\n\n"
    )
    if pairs:
        pair_rows = []
        for p in pairs:
            b, l = p["baseline"], p["loaded"]
            pair_rows.append([
                p["pair"], fmt(b["energy"]), fmt(l["energy"]),
                f'{p["change_pct"]:+.1f}%',
                f'{b["node_cpu"]:.1f}%' if b["node_cpu"] is not None else "N/A",
                f'{l["node_cpu"]:.1f}%' if l["node_cpu"] is not None else "N/A",
                l["pod_samples"],
                f'{l["pod_cpu"]:.3f}' if l["pod_cpu"] is not None else "N/A",
            ])
        write_table(
            f,
            ["Pair", "Baseline energy (kWh)", "Loaded energy (kWh)",
             "Energy change", "Baseline node CPU", "Loaded node CPU",
             "Loaded pod samples", "Loaded pod avg CPU (cores)"],
            pair_rows,
        )
        mean_b = statistics.mean(p["baseline"]["energy"] for p in pairs)
        mean_l = statistics.mean(p["loaded"]["energy"] for p in pairs)
        f.write(f"- Mean baseline energy estimate: **{fmt(mean_b)} kWh**\n")
        f.write(f"- Mean loaded energy estimate: **{fmt(mean_l)} kWh**\n")
        f.write(f"- Change between means: **{(mean_l / mean_b - 1) * 100:+.1f}%**\n\n")
    else:
        f.write("Paired results could not be assembled. Check the expected CSV files.\n\n")

    f.write("## 3. Scheduler simulation\n\n")
    f.write(
        "The scheduler benchmark uses illustrative CPU and power inputs. "
        "It compares a first-feasible-node baseline with the lowest-score "
        "feasible-node policy. It is a simulation, not a live Kubernetes "
        "scheduler integration or a measurement of energy savings.\n\n"
    )
    if benchmark_scenarios:
        scenario_rows = []
        different = 0
        gaps = []
        for scenario, policies in sorted(benchmark_scenarios.items()):
            b = policies.get("first_feasible_baseline")
            e = policies.get("energy_aware")
            if not b or not e:
                continue
            if b["selected_node"] != e["selected_node"]:
                different += 1
            gap = number(b.get("score_gap_from_best"))
            if gap is not None:
                gaps.append(gap)
            scenario_rows.append([
                scenario, b["selected_node"], e["selected_node"],
                b.get("score", "N/A"), e.get("score", "N/A"),
                b.get("score_gap_from_best", "N/A"),
            ])
        write_table(
            f,
            ["Scenario", "Baseline node", "Energy-aware node",
             "Baseline score", "Energy-aware score", "Baseline gap from best"],
            scenario_rows,
        )
        f.write(f"- Scenarios compared: **{len(scenario_rows)}**\n")
        f.write(f"- Scenarios with a different selected node: **{different}**\n")
        if gaps:
            f.write(f"- Mean baseline score gap from best feasible score: **{statistics.mean(gaps):.4f}**\n")
        f.write("\n")
    else:
        f.write("No scheduler benchmark CSV was found in `results/reports`.\n\n")

    f.write("## 4. Methodological limitations\n\n")
    f.write(
        "- CodeCarbon reports machine-level energy estimates, not direct per-pod energy.\n"
        "- Hardware RAPL energy counters were unavailable in this VM; CPU energy is estimated.\n"
        "- Background VM activity and run-to-run variation may affect results.\n"
        "- The original `loaded_03` had incomplete pod sampling; `loaded_03_repeat` is used for pair 3.\n"
        "- Minikube currently has one node, so real multi-node scheduler behavior has not been evaluated.\n"
        "- Scheduler benchmark power values are illustrative and must not be presented as measured power.\n"
        "- The baseline in the simulation is first-feasible-node selection, not Kubernetes' complete default scheduler.\n\n"
    )
    f.write("## 5. Next steps\n\n")
    f.write(
        "1. Incorporate workload characteristics and node feasibility into the policy.\n"
        "2. Define a fair multi-node evaluation or a clearly labelled simulation protocol.\n"
        "3. Evaluate scheduling decisions and performance separately from machine-level energy estimates.\n"
        "4. Keep all raw measurements and report generation reproducible.\n"
    )

print(f"Processed {len(all_rows)} CodeCarbon records.")
print(f"CSV report: {csv_path}")
print(f"Markdown report: {md_path}")
print(f"Controlled pairs included: {len(pairs)}")
print(f"Scheduler scenarios included: {len(benchmark_scenarios)}")
