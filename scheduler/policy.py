def score_node(
    cpu_percent,
    energy_watts,
    max_power_watts=100.0,
    cpu_weight=0.6,
    energy_weight=0.4,
):
    """Lower score is better; both metrics are normalized to 0–1."""
    if not 0 <= cpu_percent <= 100:
        raise ValueError("cpu_percent must be between 0 and 100")

    if energy_watts < 0:
        raise ValueError("energy_watts cannot be negative")

    if max_power_watts <= 0:
        raise ValueError("max_power_watts must be positive")

    if cpu_weight < 0 or energy_weight < 0:
        raise ValueError("weights cannot be negative")

    if not 0.999999 <= cpu_weight + energy_weight <= 1.000001:
        raise ValueError("weights must add up to 1")

    normalized_cpu = cpu_percent / 100
    normalized_power = min(energy_watts / max_power_watts, 1.0)

    return (
        cpu_weight * normalized_cpu
        + energy_weight * normalized_power
    )


def rank_nodes(nodes, max_power_watts=100.0):
    """Rank nodes from lowest score to highest score."""
    return sorted(
        nodes,
        key=lambda node: score_node(
            node["cpu_percent"],
            node["energy_watts"],
            max_power_watts=max_power_watts,
        ),
    )
