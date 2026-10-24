from policy import rank_nodes


def default_style_choice(nodes):
    """Simplified baseline: choose the first eligible node."""
    return nodes[0]


def energy_aware_choice(nodes):
    """Choose the node with the lowest policy score."""
    return rank_nodes(nodes)[0]


def main():
    nodes = [
        {
            "name": "node-a",
            "cpu_percent": 75,
            "energy_watts": 65,
        },
        {
            "name": "node-b",
            "cpu_percent": 35,
            "energy_watts": 30,
        },
        {
            "name": "node-c",
            "cpu_percent": 50,
            "energy_watts": 40,
        },
    ]

    print("Sample scheduling comparison")
    print("----------------------------")

    default_node = default_style_choice(nodes)
    energy_node = energy_aware_choice(nodes)

    print(f"Simplified default-style choice: {default_node['name']}")
    print(f"Energy-aware choice:             {energy_node['name']}")
    print("\nEnergy-aware ranking:")

    for node in rank_nodes(nodes):
        print(
            f"  {node['name']}: CPU={node['cpu_percent']}%, "
            f"estimated power={node['energy_watts']} W"
        )


if __name__ == "__main__":
    main()
