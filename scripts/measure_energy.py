import argparse
import csv
import os
import time
from datetime import datetime
from codecarbon import EmissionsTracker

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=60)
parser.add_argument("--label", required=True)
args = parser.parse_args()

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(root, "results", "raw")
os.makedirs(out_dir, exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"{args.label}_{stamp}.csv"

tracker = EmissionsTracker(
    project_name=args.label,
    output_dir=out_dir,
    output_file=filename,
    log_level="info",
)

print(f"Experiment: {args.label}")
print(f"Duration: {args.duration} seconds")
print("Energy is estimated at machine level, not per pod.")
tracker.start()
try:
    time.sleep(args.duration)
finally:
    tracker.stop()


with open(os.path.join(out_dir, filename), newline="") as f:
    record = next(csv.DictReader(f))

print(f"Estimated energy: {float(record['energy_consumed']):.9f} kWh")
print(f"Estimated emissions: {float(record['emissions']):.9f} kg CO2e")
#print(f"Estimated energy: {energy} kWh")
print(f"CSV: {os.path.join(out_dir, filename)}")
