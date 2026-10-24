"""Read-only prototype for energy-aware Kubernetes node selection.

Energy is currently a CPU-derived proxy, not measured electrical power.
This version never binds or modifies pods.
"""

import argparse
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from policy import score_node
from feasibility import eligible_nodes


def quantity_cpu(value):
    """Convert Kubernetes CPU quantities to CPU cores."""
    if not value:
        return 0.0
    value = str(value)
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000_000
    if value.endswith("u"):
        return float(value[:-1]) / 1_000_000
    if value.endswith("m"):
        return float(value[:-1]) / 1000
    return float(value)


def quantity_memory(value):
    """Convert Kubernetes memory quantities to bytes."""
    if not value:
        return 0
    value = str(value)
    units = {
        "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3,
        "Ti": 1024**4, "K": 1000, "M": 1000**2,
        "G": 1000**3, "T": 1000**4,
    }
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return int(float(value[:-len(suffix)]) * multiplier)
    return int(value)


def pod_requests(pod):
    """Sum container CPU and memory requests for a pod."""
    cpu = 0.0
    memory = 0
    for container in pod.spec.containers or []:
        resources = container.resources
        requests = resources.requests if resources and resources.requests else {}
        cpu += quantity_cpu(requests.get("cpu", "0"))
        memory += quantity_memory(requests.get("memory", "0"))
    return cpu, memory


def get_node_metrics(custom_api):
    """Return live node CPU usage percentages when Metrics Server is available."""
    try:
        result = custom_api.list_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
            _request_timeout=(3, 5),
        )
        metrics = {}
        for item in result.get("items", []):
            name = item["metadata"]["name"]
            usage_cpu = quantity_cpu(item.get("usage", {}).get("cpu", "0"))
            metrics[name] = usage_cpu
        return metrics
    except (ApiException, Exception) as exc:
        print(f"WARNING: node metrics unavailable ({exc}); using a neutral fallback.")
        return {}


def inspect_cluster(pod_cpu_request, pod_memory_request):
    config.load_kube_config()
    core = client.CoreV1Api()
    custom = client.CustomObjectsApi()

    nodes = core.list_node(_request_timeout=(3, 5)).items
    pods = core.list_pod_for_all_namespaces(_request_timeout=(3, 5)).items
    cpu_usage = get_node_metrics(custom)

    print("Mode: READ-ONLY — no pod bindings will be created.")
    print(f"Nodes discovered: {len(nodes)}")
    print(
        f"Target pod requests: CPU={pod_cpu_request:.3f} cores, "
        f"memory={pod_memory_request / 1024**2:.0f} MiB"
    )

    candidates = []
    for node in nodes:
        conditions = {c.type: c.status for c in (node.status.conditions or [])}
        name = node.metadata.name
        if conditions.get("Ready") != "True":
            print(f"Skipping {name}: node is not Ready.")
            continue

        allocatable = node.status.allocatable or {}
        total_cpu = quantity_cpu(allocatable.get("cpu", "0"))
        total_mem = quantity_memory(allocatable.get("memory", "0"))
        requested_cpu = 0.0
        requested_mem = 0

        for pod in pods:
            if pod.spec.node_name == name and pod.status.phase not in ("Succeeded", "Failed"):
                req_cpu, req_mem = pod_requests(pod)
                requested_cpu += req_cpu
                requested_mem += req_mem

        current_cpu = cpu_usage.get(name)
        if current_cpu is None:
            cpu_percent = 50.0
            print(f"WARNING: no CPU metric for {name}; using 50% fallback.")
        else:
            cpu_percent = min(100.0, 100 * current_cpu / total_cpu) if total_cpu else 100.0

        # CPU-derived illustrative proxy; not measured electrical power.
        energy_proxy_watts = 20.0 + 0.8 * cpu_percent
        candidates.append({
            "name": name,
            "allocatable_cpu": total_cpu,
            "requested_cpu": requested_cpu,
            "allocatable_memory": total_mem,
            "requested_memory": requested_mem,
            "free_cpu": max(0.0, total_cpu - requested_cpu),
            "free_memory": max(0, total_mem - requested_mem),
            "cpu_percent": cpu_percent,
            "energy_proxy_watts": energy_proxy_watts,
            "score": score_node(cpu_percent, energy_proxy_watts),
        })

    feasible = eligible_nodes(candidates, pod_cpu_request, pod_memory_request)
    print("\n===== FEASIBLE NODE RANKING =====")

    if not feasible:
        print("No Ready node fits the requested CPU and memory.")
    else:
        for item in sorted(feasible, key=lambda n: n["score"]):
            print(
                f"{item['name']}: score={item['score']:.3f}, "
                f"CPU usage={item['cpu_percent']:.1f}%, "
                f"free requested CPU={item['free_cpu']:.3f} cores, "
                f"free requested memory={item['free_memory'] / 1024**2:.0f} MiB, "
                f"energy proxy={item['energy_proxy_watts']:.1f} (illustrative units)"
            )

    print("\nNote: this checks CPU and memory requests only, not every Kubernetes scheduling constraint.")
    custom_pods = [
        pod for pod in pods
        if pod.status.phase == "Pending"
        and pod.spec.scheduler_name == "energy-aware-scheduler"
    ]
    print("\n===== PODS WAITING FOR THIS SCHEDULER =====")
    if not custom_pods:
        print("None. This prototype does not create or bind pods.")
    else:
        for pod in custom_pods:
            print(f"{pod.metadata.namespace}/{pod.metadata.name}")

    print("\nRead-only inspection complete.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod-cpu", default="100m",
                        help="CPU request, e.g. 100m or 0.5 (default: 100m)")
    parser.add_argument("--pod-memory", default="128Mi",
                        help="Memory request, e.g. 128Mi or 1Gi (default: 128Mi)")
    args = parser.parse_args()

    cpu_request = quantity_cpu(args.pod_cpu)
    memory_request = quantity_memory(args.pod_memory)
    if cpu_request < 0 or memory_request < 0:
        parser.error("pod resource requests cannot be negative")

    inspect_cluster(cpu_request, memory_request)


if __name__ == "__main__":
    main()
