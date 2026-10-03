"""Route maps: an interactive Folium map and a static PNG for the README."""
import math

import folium
import matplotlib
import networkx as nx

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd",
          "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]


def route_geometry(G, graph_nodes):
    """(lat, lon) coordinates following the streets between consecutive stops."""
    coords = []
    for u, v in zip(graph_nodes[:-1], graph_nodes[1:]):
        path = nx.shortest_path(G, u, v, weight="length")
        segment = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]
        coords.extend(segment[1:] if coords else segment)
    return coords


def folium_map(G, nodes, routes, labels, demands, path):
    depot = nodes[0]
    center = (G.nodes[depot]["y"], G.nodes[depot]["x"])
    fmap = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")

    for k, route in enumerate(routes):
        color = COLORS[k % len(COLORS)]
        coords = route_geometry(G, [nodes[i] for i in route])
        folium.PolyLine(coords, color=color, weight=4, opacity=0.8,
                        tooltip=f"Truck {k + 1}").add_to(fmap)
        for i in route[1:-1]:
            n = nodes[i]
            folium.CircleMarker(
                (G.nodes[n]["y"], G.nodes[n]["x"]), radius=5, color=color,
                fill=True, fill_opacity=0.9,
                popup=f"{labels[i]} - {demands[i]} kg").add_to(fmap)

    folium.Marker(center, popup="Depot",
                  icon=folium.Icon(color="black", icon="home")).add_to(fmap)
    fmap.save(path)


def static_map(G, nodes, routes, path, title):
    fig, ax = plt.subplots(figsize=(9, 9))

    segments = [[(G.nodes[u]["x"], G.nodes[u]["y"]),
                 (G.nodes[v]["x"], G.nodes[v]["y"])] for u, v in G.edges()]
    ax.add_collection(LineCollection(segments, colors="#d0d0d0", linewidths=0.5))

    for k, route in enumerate(routes):
        color = COLORS[k % len(COLORS)]
        coords = route_geometry(G, [nodes[i] for i in route])
        ax.plot([c[1] for c in coords], [c[0] for c in coords],
                color=color, linewidth=2.2, label=f"Truck {k + 1}")
        stops = [nodes[i] for i in route[1:-1]]
        ax.scatter([G.nodes[n]["x"] for n in stops],
                   [G.nodes[n]["y"] for n in stops],
                   s=22, color=color, zorder=3)

    depot = nodes[0]
    ax.scatter([G.nodes[depot]["x"]], [G.nodes[depot]["y"]],
               marker="*", s=320, color="black", zorder=4, label="Depot")

    ax.set_title(title)
    # one degree of longitude is shorter than one of latitude away from the equator
    ax.set_aspect(1 / math.cos(math.radians(G.nodes[depot]["y"])))
    ax.autoscale()
    ax.axis("off")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=7, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
