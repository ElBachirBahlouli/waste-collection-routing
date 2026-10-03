"""Road network loading, depot and collection point selection, distance matrix.

Two sources of road network:
- OpenStreetMap, through OSMnx: the real drivable street network of a city.
- A synthetic grid city placed at Meknes coordinates, for offline runs and tests.

Distances are shortest-path road distances on a directed graph, so one-way
streets are respected and the matrix is asymmetric.
"""
import math
import random

import networkx as nx

MEKNES_CENTER = (33.8935, -5.5547)  # (lat, lon)


# Public Overpass servers, tried in order: the main one is often overloaded.
OVERPASS_SERVERS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
]


def load_osm_network(center=MEKNES_CENTER, radius_m=3500, place=None):
    """Download the drivable street network and keep its largest strongly
    connected component, so that every node can reach every other node.

    By default the network is taken within `radius_m` metres of `center`:
    a whole administrative area (with its rural outskirts) is far larger
    than a collection round needs, and slow to download. Pass `place` to
    download a named area instead.
    """
    import osmnx as ox

    ox.settings.requests_timeout = 60
    errors = []
    for url in OVERPASS_SERVERS:
        if hasattr(ox.settings, "overpass_url"):      # OSMnx 2.x
            ox.settings.overpass_url = url
        else:                                         # OSMnx 1.x
            ox.settings.overpass_endpoint = url
        try:
            if place:
                G = ox.graph_from_place(place, network_type="drive")
            else:
                G = ox.graph_from_point(center, dist=radius_m, network_type="drive")
            break
        except Exception as exc:
            print(f"  {url} unavailable ({type(exc).__name__}), trying the next server ...")
            errors.append(exc)
    else:
        raise RuntimeError(f"All Overpass servers failed. Last error: {errors[-1]}")

    try:  # OSMnx 2.x
        G = ox.truncate.largest_component(G, strongly=True)
    except AttributeError:  # OSMnx 1.x
        G = ox.utils_graph.get_largest_component(G, strongly=True)
    return G


def build_synthetic_network(rows=25, cols=25, spacing_m=120, seed=42,
                            center=MEKNES_CENTER):
    """Grid city with irregular block lengths and a few removed street
    directions (one-way streets), always kept strongly connected."""
    rng = random.Random(seed)
    lat0, lon0 = center
    dlat = spacing_m / 111_320
    dlon = spacing_m / (111_320 * math.cos(math.radians(lat0)))

    G = nx.DiGraph()
    for r in range(rows):
        for c in range(cols):
            G.add_node(r * cols + c,
                       y=lat0 + (r - rows / 2) * dlat,
                       x=lon0 + (c - cols / 2) * dlon)

    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 < rows and c2 < cols:
                    length = spacing_m * rng.uniform(0.9, 1.4)
                    a, b = r * cols + c, r2 * cols + c2
                    G.add_edge(a, b, length=length)
                    G.add_edge(b, a, length=length)

    edges = list(G.edges(data="length"))
    rng.shuffle(edges)
    target = len(edges) // 12
    removed = 0
    for u, v, length in edges:
        if removed >= target:
            break
        G.remove_edge(u, v)
        if nx.is_strongly_connected(G):
            removed += 1
        else:
            G.add_edge(u, v, length=length)
    return G


def nearest_node(G, lat, lon):
    """Closest graph node to a (lat, lon) point, by planar approximation."""
    coslat = math.cos(math.radians(lat))
    return min(
        G.nodes,
        key=lambda n: (G.nodes[n]["y"] - lat) ** 2
        + ((G.nodes[n]["x"] - lon) * coslat) ** 2,
    )


def select_depot_and_points(G, n_points, seed=42, depot_latlon=None):
    """Depot at the given coordinates (default: centre of the network),
    and `n_points` distinct collection points sampled among street nodes."""
    if depot_latlon is None:
        lat = sum(d["y"] for _, d in G.nodes(data=True)) / G.number_of_nodes()
        lon = sum(d["x"] for _, d in G.nodes(data=True)) / G.number_of_nodes()
        depot_latlon = (lat, lon)
    depot = nearest_node(G, *depot_latlon)

    candidates = [n for n in G.nodes if n != depot]
    if n_points > len(candidates):
        raise ValueError(f"Network only has {len(candidates)} usable nodes.")
    points = random.Random(seed).sample(candidates, n_points)
    return depot, points


def distance_matrix(G, nodes):
    """Integer road distances in metres between all pairs of `nodes`."""
    n = len(nodes)
    matrix = [[0] * n for _ in range(n)]
    for i, src in enumerate(nodes):
        lengths = nx.single_source_dijkstra_path_length(G, src, weight="length")
        for j, tgt in enumerate(nodes):
            if i != j:
                if tgt not in lengths:
                    raise ValueError(f"Node {tgt} unreachable from {src}.")
                matrix[i][j] = int(round(lengths[tgt]))
    return matrix
