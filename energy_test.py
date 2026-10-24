from codecarbon import EmissionsTracker
import time
import os
# Create the output directory if it doesn't exist
output_dir = os.path.expanduser("~/energy_results")
os.makedirs(output_dir, exist_ok=True)

tracker = EmissionsTracker(
    project_name="kubernetes_energy_test",
    output_dir=output_dir,
    log_level="info"
)

tracker.start()

try:
    print("Running a 60-second energy-estimation test...")
    time.sleep(60)
finally:
    energy_kwh = tracker.stop()

print(f"Estimated energy: {energy_kwh} kWh")
