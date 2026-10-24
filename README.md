# Energy-Aware Scheduling of AI Workloads in Kubernetes

## Current stage
This repository organizes an existing Minikube experiment. It currently
supports a CPU-loop workload and CodeCarbon machine-level energy estimation.
An energy-aware scheduling policy is still future work.

## Requirements
- Ubuntu VM with Docker and Minikube
- kubectl and Helm
- Existing `cpu-test` Kubernetes deployment
- Python environment at `venv/` with CodeCarbon installed

## Commands
- `./project.sh start` — start/reuse Minikube and display pods
- `./project.sh status` — inspect cluster, pods, node metrics and result files
- `./project.sh baseline` — temporarily scale the CPU test to zero, measure,
  then restore its original replica count
- `./project.sh load-test` — ensure the CPU test is running and measure
- `./project.sh report` — build CSV and Markdown summaries
- `./project.sh stop` — stop the CPU test workload only
- `./project.sh cluster-stop` — stop Minikube without deleting its resources

## Results
New raw CSV files are saved in `results/raw/`. Generated reports are saved in
`results/reports/`. Earlier results are copied into `results/raw/`; the original
files in `~/energy_results/` are preserved.

## Measurement limitation
CodeCarbon estimates energy for the machine visible to the VM. It does not
directly measure the energy consumed by an individual Kubernetes pod.
Baseline and loaded measurements should be repeated under controlled conditions.

## Research status
The Kubernetes workload and monitoring stack are deployed. The project's
energy-aware scheduling algorithm, policy comparison and evaluation remain
to be implemented.
