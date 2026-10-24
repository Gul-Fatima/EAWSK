from codecarbon import EmissionsTracker
import time
import os
from datetime import datetime

output_dir = os.path.expanduser("~/energy_results")
os.makedirs(output_dir, exist_ok=True)

run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

tracker = EmissionsTracker(
    project_name="kubernetes_cpu_loaded",
    output_dir=output_dir,
    output_file=f"cpu_loaded_{run_id}.csv",
    log_level="info"
)

print("Starting 60-second measurement with Kubernetes CPU workload active.")
print("Keep the cpu-test pod running during the measurement.")

tracker.start()
try:
    time.sleep(60)
finally:
    energy_kwh = tracker.stop()

print(f"Estimated machine energy: {energy_kwh} kWh")
print(f"Results saved in: {output_dir}")
