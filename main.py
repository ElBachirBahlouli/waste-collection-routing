"""Predict-then-optimize waste collection routing.

Examples:
    python main.py                        # Meknes, 3.5 km around the centre
    python main.py --radius 5000          # a larger area
    python main.py --synthetic            # offline demo, no download
"""
import argparse
import csv
import math
import os
import time

from routing import forecast, network, solver, visualize


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--city", default="Meknes, Morocco",
                   help="City name used in the report and maps.")
    p.add_argument("--center", default="33.8935,-5.5547",
                   help='Centre of the area to download, as "lat,lon" (default: Meknes).')
    p.add_argument("--radius", type=int, default=3500,
                   help="Radius of the area to download, in metres.")
    p.add_argument("--place", default=None,
                   help="Download a whole named area instead of a radius (slower).")
    p.add_argument("--synthetic", action="store_true",
                   help="Use a synthetic grid city instead of OpenStreetMap.")
    p.add_argument("--depot", default=None,
                   help='Depot as "lat,lon". Default: centre of the network.')
    p.add_argument("--points", type=int, default=40,
                   help="Number of collection points.")
    p.add_argument("--vehicles", type=int, default=5,
                   help="Available trucks (raised automatically if capacity requires it).")
    p.add_argument("--capacity", type=int, default=2000,
                   help="Truck capacity in kg.")
    p.add_argument("--buffer", type=float, default=0.10,
                   help="Safety margin added to forecast volumes (0.10 = +10%%).")
    p.add_argument("--weeks", type=int, default=8,
                   help="Weeks of simulated history.")
    p.add_argument("--time-limit", type=int, default=15,
                   help="Solver time limit in seconds.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="results")
    return p.parse_args()


def load_network(args):
    if args.synthetic:
        return network.build_synthetic_network(seed=args.seed), \
            "Synthetic grid city (Meknes coordinates) - demo data"
    lat, lon = (float(x) for x in args.center.split(","))
    area = args.place or f"{args.radius / 1000:.1f} km around ({lat}, {lon})"
    print(f"Downloading road network from OpenStreetMap: {area} ...")
    try:
        G = network.load_osm_network(center=(lat, lon), radius_m=args.radius,
                                     place=args.place)
    except Exception as exc:
        # No silent fallback: results on a synthetic grid must never be
        # mistaken for results on the real city.
        raise SystemExit(
            f"\nOpenStreetMap download failed: {exc}\n"
            "Check your internet connection and retry in a few minutes, "
            "or run the offline demo with --synthetic.")
    label = args.place or f"{args.city} ({args.radius / 1000:.1f} km around the centre)"
    return G, label


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    # 1. Road network, depot, collection points, road distances
    G, place_label = load_network(args)
    depot_latlon = None
    if args.depot:
        lat, lon = (float(x) for x in args.depot.split(","))
        depot_latlon = (lat, lon)
    depot, points = network.select_depot_and_points(
        G, args.points, args.seed, depot_latlon)
    nodes = [depot] + points
    print(f"Network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print("Computing road distance matrix ...")
    dist = network.distance_matrix(G, nodes)

    # 2. Demand: backtest the forecaster, then forecast tomorrow
    history = forecast.simulate_history(len(points), args.weeks, args.seed)
    bt = forecast.backtest(history)
    predicted = forecast.forecast_next_day(history)
    labels = ["Depot"] + list(predicted.keys())
    demands = [0] + [math.ceil(v * (1 + args.buffer)) for v in predicted.values()]
    print(f"Forecast backtest MAPE: Holt-Winters {bt['mape_holt_winters']:.1f}% "
          f"vs seasonal naive {bt['mape_seasonal_naive']:.1f}%")

    # 3. Optimization
    total_demand = sum(demands)
    min_vehicles = math.ceil(total_demand / args.capacity)
    vehicles = max(args.vehicles, min_vehicles)
    if vehicles > args.vehicles:
        print(f"Capacity requires {vehicles} trucks; raised from {args.vehicles}.")
    print(f"Solving CVRP ({len(points)} points, {vehicles} trucks, "
          f"{args.time_limit}s) ...")
    t0 = time.time()
    routes, unserved = solver.solve_cvrp(
        dist, demands, vehicles, args.capacity, args.time_limit)
    solve_time = time.time() - t0

    # 4. Benchmark against the nearest-neighbour heuristic
    baseline = solver.greedy_baseline(dist, demands, args.capacity)
    opt_km = solver.total_distance(routes, dist) / 1000
    base_km = solver.total_distance(baseline, dist) / 1000
    reduction = (base_km - opt_km) / base_km * 100

    # 5. Outputs
    map_html = os.path.join(args.output, "routes_map.html")
    map_png = os.path.join(args.output, "routes.png")
    visualize.folium_map(G, nodes, routes, labels, demands, map_html)
    visualize.static_map(G, nodes, routes, map_png,
                         f"Optimized collection routes - {place_label}")

    with open(os.path.join(args.output, "routes.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["truck", "stop_order", "point", "demand_kg"])
        for k, route in enumerate(routes, 1):
            for order, i in enumerate(route):
                w.writerow([k, order, labels[i], demands[i]])

    lines = [
        "# Results",
        "",
        f"- **Network:** {place_label} - {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges",
        f"- **Collection points:** {len(points)} - total forecast demand "
        f"{total_demand:,} kg (with a {args.buffer:.0%} safety buffer)",
        f"- **Trucks:** {len(routes)} used of {vehicles} available - "
        f"capacity {args.capacity:,} kg each",
        "",
        "## Forecasting (backtest on the last week)",
        "",
        "| Model | Mean absolute percentage error |",
        "|---|---|",
        f"| Holt-Winters (damped trend, weekly seasonality) | "
        f"{bt['mape_holt_winters']:.1f}% |",
        f"| Seasonal naive (same weekday last week) | "
        f"{bt['mape_seasonal_naive']:.1f}% |",
        "",
        "## Routing",
        "",
        "| Plan | Total distance |",
        "|---|---|",
        f"| Nearest-neighbour heuristic (baseline) | {base_km:.1f} km |",
        f"| OR-Tools CVRP, guided local search | {opt_km:.1f} km |",
        "",
        f"**Distance reduction vs baseline: {reduction:.1f}%** "
        f"(solved in {solve_time:.0f} s)",
        "",
        "| Truck | Stops | Load (kg) | Distance (km) |",
        "|---|---|---|---|",
    ]
    for k, route in enumerate(routes, 1):
        lines.append(f"| {k} | {len(route) - 2} | "
                     f"{solver.route_load(route, demands):,} | "
                     f"{solver.route_distance(route, dist) / 1000:.1f} |")
    if unserved:
        lines += ["", f"Unserved points: {', '.join(labels[i] for i in unserved)}"]
    lines += [
        "",
        "Waste volumes are simulated and collection points are sampled street "
        "nodes. The baseline is a heuristic, not the city's current routes. "
        "See the README for all assumptions.",
        "",
        "![Optimized routes](routes.png)",
    ]
    with open(os.path.join(args.output, "RESULTS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print(f"Baseline: {base_km:.1f} km | Optimized: {opt_km:.1f} km | "
          f"Reduction: {reduction:.1f}%")
    if unserved:
        print(f"WARNING - unserved points: {[labels[i] for i in unserved]}")
    print(f"Results written to {args.output}/ "
          "(RESULTS.md, routes.png, routes_map.html, routes.csv)")


if __name__ == "__main__":
    main()
