import argparse
import csv
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from codecarbon import EmissionsTracker

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "run_id",
    "label",
    "timestamp",
    "elapsed_seconds",
    "metric_type",
    "namespace",
    "resource_name",
    "cpu_cores",
    "cpu_percent",
    "memory",
    "memory_percent",
    "status",
]


def run_kubectl(args):
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    ).stdout


def cpu_to_cores(value):
    if value.endswith("m"):
        return float(value[:-1]) / 1000
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000_000
    return float(value)


def collect_metrics(writer, run_id, label, start):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    elapsed = round(time.monotonic() - start, 2)
    records = []

    try:
        output = run_kubectl(["top", "nodes", "--no-headers"])
        for line in output.strip().splitlines():
            cols = line.split()
            if len(cols) < 5:
                continue
            name, cpu, cpu_pct, memory, memory_pct = cols[:5]
            records.append({
                "metric_type": "node",
                "namespace": "",
                "resource_name": name,
                "cpu_cores": cpu_to_cores(cpu),
                "cpu_percent": cpu_pct.rstrip("%"),
                "memory": memory,
                "memory_percent": memory_pct.rstrip("%"),
                "status": "ok",
            })
    except (subprocess.SubprocessError, ValueError) as exc:
        records.append({
            "metric_type": "node",
            "resource_name": "",
            "status": f"error: {type(exc).__name__}",
        })

    try:
        output = run_kubectl(["top", "pods", "-A", "--no-headers"])
        for line in output.strip().splitlines():
            cols = line.split()
            if len(cols) < 4:
                continue
            namespace, name, cpu, memory = cols[:4]
            records.append({
                "metric_type": "pod",
                "namespace": namespace,
                "resource_name": name,
                "cpu_cores": cpu_to_cores(cpu),
                "cpu_percent": "",
                "memory": memory,
                "memory_percent": "",
                "status": "ok",
            })
    except (subprocess.SubprocessError, ValueError) as exc:
        records.append({
            "metric_type": "pod",
            "resource_name": "",
            "status": f"error: {type(exc).__name__}",
        })

    for record in records:
        writer.writerow({
            "run_id": run_id,
            "label": label,
            "timestamp": timestamp,
            "elapsed_seconds": elapsed,
            **record,
        })

    return sum(r.get("status") == "ok" for r in records)


def main():
    parser = argparse.ArgumentParser(
        description="Measure machine-level energy and Kubernetes resource metrics."
    )
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    if args.duration < 15:
        parser.error("--duration must be at least 15 seconds")
    if args.interval < 1:
        parser.error("--interval must be at least 1 second")

    label = re.sub(r"[^A-Za-z0-9_-]", "_", args.label)
    run_id = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")

    metrics_path = OUTPUT_DIR / f"resource_metrics_{label}_{run_id}.csv"
    energy_name = f"energy_{label}_{run_id}.csv"

    tracker = EmissionsTracker(
        project_name=label,
        output_dir=str(OUTPUT_DIR),
        output_file=energy_name,
        log_level="warning",
    )

    print(f"Run ID: {run_id}")
    print(f"Label: {label}")
    print(f"Duration: {args.duration}s; sampling interval: {args.interval}s")
    print("Energy values are machine-level CodeCarbon estimates, not per-pod energy.")
    print(f"Resource metrics: {metrics_path}")

    start = None
    tracker_started = False
    sample_count = 0

    try:
        with metrics_path.open("x", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            f.flush()

            tracker.start()
            tracker_started = True
            start = time.monotonic()
            deadline = start + args.duration

            while time.monotonic() < deadline:
                good = collect_metrics(writer, run_id, label, start)
                f.flush()
                sample_count += 1
                print(
                    f"Sample {sample_count}: {good} metric records collected"
                )

                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(args.interval, remaining))
    finally:
        if tracker_started:
            tracker.stop()

    print(f"Completed samples: {sample_count}")
    print(f"Resource metrics CSV: {metrics_path}")
    print(f"CodeCarbon CSV: {OUTPUT_DIR / energy_name}")


if __name__ == "__main__":
    main()
