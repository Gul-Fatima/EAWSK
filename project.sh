#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/venv/bin/python"
DEPLOYMENT="cpu-test"

usage() {
  echo "Usage: ./project.sh {start|status|baseline|load-test|report|stop|cluster-stop}"
}

check_tools() {
  command -v minikube >/dev/null || { echo "minikube is not installed"; exit 1; }
  command -v kubectl >/dev/null || { echo "kubectl is not installed"; exit 1; }
  [[ -x "$PYTHON" ]] || { echo "Project Python environment not found: $PYTHON"; exit 1; }
}

ensure_cluster() {
  check_tools

  if ! minikube status 2>/dev/null | grep -q 'host: Running'; then
    minikube start || return 1
  else
    echo "Minikube is already running; skipping startup."
  fi

  kubectl wait --for=condition=Ready node/minikube --timeout=180s
}

ensure_deployment() {
  kubectl get deployment "$DEPLOYMENT" >/dev/null 2>&1 || {
    echo "Deployment '$DEPLOYMENT' not found. No resources were created."
    exit 1
  }
}

restore_replicas() {
  kubectl scale deployment/"$DEPLOYMENT" --replicas="$OLD_REPLICAS" >/dev/null 2>&1 || true
  if [[ "$OLD_REPLICAS" -gt 0 ]]; then
    kubectl rollout status deployment/"$DEPLOYMENT" --timeout=180s || true
  fi
}

case "${1:-}" in
  start)
    ensure_cluster
    echo "Cluster is ready. Existing monitoring and workloads are preserved."
    kubectl get pods -A
    ;;

  status)
    check_tools
    minikube status || true
    kubectl get pods -A
    kubectl top nodes || true
    echo
    echo "Recent project result files:"
    find "$ROOT/results" -type f -maxdepth 3 -print
    ;;

  baseline)
    ensure_cluster
    ensure_deployment
    OLD_REPLICAS="$(kubectl get deployment "$DEPLOYMENT" -o jsonpath='{.spec.replicas}')"
    trap restore_replicas EXIT
    kubectl scale deployment/"$DEPLOYMENT" --replicas=0
    echo "Allowing 10 seconds for the test workload to stop..."
    sleep 10
    "$PYTHON" "$ROOT/scripts/measure_energy.py" --duration 60 --label baseline
    ;;

  load-test)
    ensure_cluster
    ensure_deployment
    kubectl scale deployment/"$DEPLOYMENT" --replicas=1
    kubectl rollout status deployment/"$DEPLOYMENT" --timeout=180s
    echo "Current pod metrics (if available):"
    kubectl top pods || true
    "$PYTHON" "$ROOT/scripts/measure_energy.py" --duration 60 --label cpu_loaded
    ;;

  report)
    check_tools
    "$PYTHON" "$ROOT/scripts/make_report.py"
    ;;

  stop)
    check_tools
    ensure_deployment
    kubectl scale deployment/"$DEPLOYMENT" --replicas=0
    echo "CPU test workload stopped. Cluster and monitoring remain running."
    ;;

  cluster-stop)
    check_tools
    echo "Stopping Minikube. Kubernetes resources are not being deleted."
    minikube stop
    ;;

  *)
    usage
    exit 1
    ;;
esac
