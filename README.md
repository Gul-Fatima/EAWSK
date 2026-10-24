# Energy-Aware Scheduling of AI Workloads in Kubernetes (EAWSK)

## 1. Project Overview

EAWSK investigates energy-aware scheduling of AI workloads in Kubernetes. The research explores how scheduling decisions can affect workload placement, resource utilization, and potentially energy consumption.

The repository contains two related experimental components:

1. **Kubernetes measurement experiment** — runs a CPU workload in Minikube and collects machine-level energy estimates using CodeCarbon.
2. **Trace-driven scheduling experiment** — uses a sampled Alibaba GPU cluster trace to compare placement policies under GPU-type, GPU-capacity, and CPU-capacity constraints.

These components serve different purposes. CodeCarbon estimates energy for the machine visible to the VM, while the trace-driven experiment evaluates simulated placement decisions. They should not be treated as a single validated energy measurement.

## 2. Repository Structure

```text
energy-kubernetes/
├── README.md
├── project.sh
├── kubernetes/
├── scheduler/
├── tests/
├── data/
│   ├── sample/
│   └── reference/
├── results/
│   ├── raw/
│   └── reports/
├── scripts/
├── docs/
├── ui/
└── venv/
```

Some directories may contain additional files. The descriptions below cover the main components used by the current project.

| Path | Purpose |
|---|---|
| `README.md` | Project overview, setup, commands, data description, and research limitations. |
| `project.sh` | Entry point for common Minikube, workload, measurement, and reporting operations. |
| `kubernetes/` | Kubernetes configuration and workload-related project files. |
| `scheduler/` | Scheduling policies, feasibility checks, simulations, benchmarks, and live scheduler code. |
| `tests/` | Automated tests for scheduler and simulator behavior. |
| `data/sample/` | Sampled Alibaba GPU pod and server datasets used in trace-driven experiments. |
| `data/reference/` | Reference power and energy profiles derived from NLR Llama 3 70B inference measurements. |
| `results/raw/` | Raw measurement and experiment result CSV files. |
| `results/reports/` | Generated summaries, benchmark outputs, and trace-experiment reports. |
| `scripts/` | Supporting automation and utility scripts. |
| `docs/` | Research notes, documentation, and supporting material. |
| `ui/` | User-interface-related project files, if used by the current workflow. |
| `venv/` | Local Python virtual environment; this is an environment directory, not source code. |

## 3. Scheduler Files

| File | Purpose |
|---|---|
| `scheduler/policy.py` | Defines the existing node scoring function and node ranking logic. Its current score combines normalized CPU utilization and a supplied power value using configurable weights. |
| `scheduler/simulate.py` | Demonstrates a small scheduling comparison using hard-coded example nodes. |
| `scheduler/benchmark.py` | Runs illustrative scheduling scenarios and compares baseline and energy-aware choices. Its example power values are not measured values. |
| `scheduler/feasibility.py` | Checks whether a node has sufficient unrequested CPU and memory for a pod request. |
| `scheduler/trace_experiment.py` | Runs the trace-driven placement experiment on the sampled Alibaba pod and server CSV files, when present. |
| `scheduler/live_scheduler.py` | Entry point for the live Kubernetes scheduler workflow. Its behavior depends on the current implementation and cluster configuration. |
| `tests/test_simulator.py` | Tests the existing simulator's first-node baseline choice and energy-aware ranking behavior. |

The toy simulator and benchmark are illustrative tools. They should not be interpreted as results from a production Kubernetes scheduling experiment.

## 4. Input Data and Provenance

### Alibaba GPU Cluster Trace sample

Source repository:  
https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2026

Schema documentation:  
https://github.com/alibaba/clusterdata/blob/master/cluster-trace-gpu-v2026/docs/schema.md

| File | Contents |
|---|---|
| `data/sample/alibaba_pods_sample_2000.csv` | 1,998 sampled GPU pod records, including pod and workload identifiers, GPU type, GPU request, GPU-memory request, CPU request, workload/model labels, utilization fields, and scheduling-delay information. |
| `data/sample/alibaba_servers_sample.csv` | 240 sampled server records, including server and cluster identifiers, GPU type, GPU count, and CPU capacity. |

The pod sample was selected using stratified sampling by GPU type with a fixed random seed. The server sample contains 20 servers per GPU type across 12 GPU types.

**Important data limitations:**

- The pod sample is not a chronological workload replay. Its row order must not be interpreted as actual arrival order.
- The pod and server samples are not a complete representation of the original cluster.
- GPU types are treated as distinct resource types; requests must match a compatible server type.
- Fractional GPU requests must be preserved rather than rounded to whole GPUs.
- Some GPU types have more sampled demand than sampled capacity. Pending pods are therefore an expected possible outcome.
- GPU-memory request units and corresponding server memory capacities must be verified before GPU-memory feasibility can be enforced.
- Trace observations should not automatically be interpreted as new job arrivals or as proof that a pod was running or completed.

### NLR reference energy profiles

Source catalog:  
https://data.nlr.gov/submissions/312

OpenEI dataset page:  
https://data.openei.org/submissions/8651

| File | Contents |
|---|---|
| `data/reference/nlr_offline_llama3_70b_energy_profiles.csv` | 1,200 offline Llama 3 70B inference profiles with batch, timing, power, and derived energy information. |
| `data/reference/nlr_offline_llama3_70b_energy_summary.csv` | Aggregated descriptive statistics for the reference profiles. |

The derived energy field uses:

`estimated_energy_Wh = mean_power_W * elapsed_seconds / 3600`

These profiles describe the NLR measurement workload and hardware. They are reference data, not direct power measurements of the Alibaba GPU server types. They must not be applied to Alibaba servers as if the hardware and workloads were equivalent without a justified mapping and validation.

## 5. Environment and Requirements

The existing measurement workflow expects:

- Ubuntu or a compatible Linux environment
- Docker
- Minikube
- `kubectl`
- Helm
- Python and the repository's virtual environment
- CodeCarbon installed in the Python environment for the machine-level energy-estimation workflow

The live scheduling workflow additionally depends on the Kubernetes cluster and scheduler configuration being available.

Activate the environment if needed:

```bash
source venv/bin/activate
```

## 6. Existing Kubernetes Measurement Commands

Run these commands from the repository root:

| Command | Purpose |
|---|---|
| `./project.sh start` | Start or reuse Minikube and display pods. |
| `./project.sh status` | Inspect cluster status, pods, node metrics, and result files. |
| `./project.sh baseline` | Temporarily scale the CPU test to zero, measure, and restore its original replica count. |
| `./project.sh load-test` | Ensure the CPU test is running and measure. |
| `./project.sh report` | Build CSV and Markdown summaries. |
| `./project.sh stop` | Stop the CPU test workload only. |
| `./project.sh cluster-stop` | Stop Minikube without deleting its resources. |

These commands belong to the existing Kubernetes measurement workflow; they do not, by themselves, run the trace-driven scheduling comparison.

## 7. Trace-Driven Placement Experiment

When `scheduler/trace_experiment.py` is available, run it from the repository root:

```bash
venv/bin/python -u scheduler/trace_experiment.py
```

The experiment compares three placement strategies:

1. **First-fit baseline** — selects the first feasible server in the inventory.
2. **Resource-aware policy** — prefers feasible servers with lower projected maximum CPU/GPU utilization.
3. **Preliminary energy-aware heuristic** — favors servers that already have higher utilization, attempting to consolidate requests.

Each policy receives the same input pod order and a fresh copy of the server inventory. Feasibility currently checks GPU type, GPU quantity, and CPU capacity.

The script writes timestamped CSV outputs to `results/reports/`:

- `trace_assignments_*.csv` — per-pod placement or pending status for each policy.
- `trace_summary_*.csv` — placement counts, placement rate, and aggregate GPU/CPU capacity utilization.

The exact output filenames include a run timestamp.

**The preliminary energy-aware policy is a consolidation heuristic, not a validated energy model.** The trace experiment does not currently calculate energy in Wh or kWh, and it must not be used to claim measured energy savings. GPU-memory feasibility is also not enforced until its units and corresponding capacities are validated.

## 8. Tests

Run the existing unit tests with:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Tests help verify implemented behavior but do not establish that a scheduling policy reduces real-world energy consumption.

## 9. Results and Reproducibility

- Raw measurement CSV files are stored in `results/raw/`.
- Generated reports and trace-experiment outputs are stored in `results/reports/`.
- Earlier measurement files were copied into `results/raw/`; the original files in `~/energy_results/` are preserved.
- Input datasets should remain unchanged during policy comparisons.
- Policies should use the same workload, server inventory, resource constraints, and input order.
- Record the policy configuration, assumptions, and code version for each reported result.
- Report pending pods alongside successful placements; do not hide infeasible workloads to improve a policy's apparent performance.

## 10. Measurement and Modeling Limitations

**Machine-level energy estimation:** CodeCarbon estimates energy for the machine visible to the VM. It does not directly measure the energy consumed by an individual Kubernetes pod.

**Power assumptions:** Illustrative `energy_watts` values in the toy simulator and benchmark are not calibrated server measurements.

**Energy accounting:** Energy is the integral of power over time. CPU utilization or GPU utilization alone is not an energy measurement. A defensible model requires documented power assumptions, a justified mapping to the relevant hardware/workload, and sensitivity analysis or validation against measurements.

**Reference-data transfer:** NLR inference profiles and Alibaba cluster observations come from different data sources and may represent different hardware and workloads. Any use of NLR values in an Alibaba-based model requires an explicit, justified mapping.

**Placement and feasibility:** A policy's placement rate should be interpreted together with pending pods, resource utilization, and the constraints used. Better placement or higher utilization alone does not prove lower energy consumption.

## 11. Current Research Status

The repository contains the existing Minikube CPU workload and CodeCarbon measurement workflow, toy scheduling examples, resource-feasibility logic, sampled Alibaba GPU trace data, and NLR inference energy-reference profiles.

The trace-driven placement comparison is being developed separately from the live Kubernetes workflow. Further work is required to validate GPU-memory units, establish a defensible power model, conduct sensitivity analysis, and evaluate whether energy-aware decisions improve energy outcomes without compromising placement feasibility.

Until these steps are completed, results should be described as **simulated placement outcomes or modeled estimates**, as appropriate—not as measured real-world energy savings.
