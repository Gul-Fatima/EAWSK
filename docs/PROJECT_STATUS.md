# Project Status

## Project
Energy-Aware Scheduling of AI Workloads in Kubernetes

## Completed infrastructure
- Ubuntu VM and Minikube Kubernetes cluster configured.
- Metrics Server operational; `kubectl top` returns node and pod metrics.
- CPU-test BusyBox workload deployed as `cpu-test`.
- Prometheus and Grafana deployed using Helm.
- Grafana dashboard includes node CPU, pod CPU, pod memory, and node memory panels.
- CodeCarbon and Kubernetes resource-metric experiment runner created.
- Raw results are stored in `results/raw/`.
- Report generator creates `results/reports/energy_summary.md` and `energy_summary.csv`.

## Completed workload experiments
- Three baseline runs: `baseline_01`, `baseline_02`, `baseline_03`.
- Loaded runs: `loaded_01`, `loaded_02`, and `loaded_03_repeat`.
- Original `loaded_03` is preserved but excluded from paired analysis because pod sampling was incomplete.
- Mean baseline machine-level energy estimate: approximately 0.000229474 kWh.
- Mean loaded machine-level energy estimate: approximately 0.000383425 kWh.
- Difference between these means: approximately +67.1%.
- These are preliminary estimates, not direct measurements or per-pod energy values.

## Completed scheduler simulation
- CPU/power weighted scoring policy implemented in `scheduler/policy.py`.
- Feasibility-aware multi-scenario benchmark implemented in `scheduler/benchmark.py`.
- Eight unit tests pass.
- Six illustrative scenarios executed.
- Energy-aware policy selected a different node in five of six scenarios and selected a lowest-score feasible node in all six.
- Scheduler benchmark CSV is stored in `results/reports/`.
- Simulation inputs are illustrative; the baseline is first-feasible-node selection, not the full Kubernetes default scheduler.

## Current limitations
- Minikube currently has one node, so real multi-node scheduling has not been evaluated.
- RAPL hardware energy counters are unavailable in the VM.
- CodeCarbon therefore estimates machine-level energy; energy is not attributed to individual pods.
- VM background activity and sampling variation may affect measurements.
- The current CPU-test workload is a CPU busy loop, not an AI workload.
- The scheduling policy has not been integrated with the live Kubernetes scheduler.

## Remaining work
1. Improve the scoring policy to include workload characteristics and feasible-node conditions.
2. Define and document a fair multi-node simulation or deploy a resource-feasible multi-node test environment.
3. Compare the proposed policy with a clearly defined baseline across repeatable scenarios.
4. Evaluate scheduling decisions and performance separately from machine-level energy estimates.
5. Replace or supplement the CPU-test workload with a reproducible AI workload.
6. Regenerate and review the report after each meaningful experiment.
7. Prepare the final research report and supervisor demonstration.
