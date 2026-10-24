"""Resource-request feasibility checks for energy-aware node ranking."""


def node_fits_pod(
    node,
    pod_cpu_request,
    pod_memory_request,
):
    """Return whether a node has enough unrequested CPU and memory.

    The node dictionary must provide:
      - allocatable_cpu
      - requested_cpu
      - allocatable_memory
      - requested_memory

    CPU values are in cores; memory values are in bytes.
    This checks resource requests only, not every Kubernetes scheduling rule.
    """
    if pod_cpu_request < 0 or pod_memory_request < 0:
        raise ValueError("Pod resource requests cannot be negative")

    required = (
        "allocatable_cpu",
        "requested_cpu",
        "allocatable_memory",
        "requested_memory",
    )
    missing = [key for key in required if key not in node]
    if missing:
        raise ValueError(f"Missing node resource fields: {', '.join(missing)}")

    free_cpu = max(0.0, node["allocatable_cpu"] - node["requested_cpu"])
    free_memory = max(
        0, node["allocatable_memory"] - node["requested_memory"]
    )

    return (
        free_cpu >= pod_cpu_request
        and free_memory >= pod_memory_request
    )


def eligible_nodes(
    nodes,
    pod_cpu_request,
    pod_memory_request,
):
    """Return only nodes that satisfy the pod's CPU and memory requests."""
    return [
        node
        for node in nodes
        if node_fits_pod(node, pod_cpu_request, pod_memory_request)
    ]
