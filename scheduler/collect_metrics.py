import csv
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "node_metrics.csv"


def collect_node_metrics():
    result = subprocess.run(
        ["kubectl", "top", "nodes", "--no-headers"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    records = []

    for line in result.stdout.strip().splitlines():
        columns = line.split()

        if len(columns) < 5:
            continue

        node, cpu, cpu_percent, memory, memory_percent = columns[:5]

        records.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "node": node,
            "cpu_cores": cpu,
            "cpu_percent": cpu_percent.rstrip("%"),
            "memory": memory,
            "memory_percent": memory_percent.rstrip("%"),
        })

    return records


def main():
    records = collect_node_metrics()

    if not records:
        raise RuntimeError("No node metrics returned by kubectl")

    fields = [
        "timestamp",
        "node",
        "cpu_cores",
        "cpu_percent",
        "memory",
        "memory_percent",
    ]

    file_exists = OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0

    with OUTPUT_FILE.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)

        if not file_exists:
            writer.writeheader()

        writer.writerows(records)

    for record in records:
        print(
            f"{record['node']}: CPU {record['cpu_percent']}%, "
            f"memory {record['memory_percent']}%"
        )

    print(f"Saved {len(records)} node record(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
