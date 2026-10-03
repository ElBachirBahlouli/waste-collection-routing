"""Capacitated Vehicle Routing Problem (CVRP) solver and baseline.

Node 0 is the depot. Every other node is a collection point with a demand
in kg. Each truck has the same capacity, starts and ends at the depot, and the
objective is to minimise the total distance driven.
"""
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_cvrp(dist, demands, n_vehicles, capacity, time_limit_s=15, depot=0):
    """Solve the CVRP with OR-Tools (guided local search).

    Returns (routes, unserved). Each route is a list of node indices starting
    and ending at the depot. A point is only left unserved if capacity makes
    serving it impossible: dropping it carries a penalty far above any route
    cost, so an infeasible instance is reported instead of failing silently.
    """
    manager = pywrapcp.RoutingIndexManager(len(dist), n_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def distance_cb(from_index, to_index):
        return dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit = routing.RegisterTransitCallback(distance_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    def demand_cb(from_index):
        return demands[manager.IndexToNode(from_index)]

    demand_index = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        demand_index, 0, [capacity] * n_vehicles, True, "Capacity")

    penalty = 10 * sum(max(row) for row in dist)
    for node in range(len(dist)):
        if node != depot:
            routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    params.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise RuntimeError("OR-Tools found no solution within the time limit.")

    routes = []
    for v in range(n_vehicles):
        index = routing.Start(v)
        route = []
        while not routing.IsEnd(index):
            route.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))
        if len(route) > 2:  # skip trucks that stay at the depot
            routes.append(route)

    served = {n for r in routes for n in r}
    unserved = [n for n in range(len(dist)) if n != depot and n not in served]
    return routes, unserved


def greedy_baseline(dist, demands, capacity, depot=0):
    """Nearest-neighbour heuristic, a stand-in for manual planning: each truck
    drives to the closest unvisited point that still fits, and returns to the
    depot when nothing else fits."""
    unvisited = set(range(len(dist))) - {depot}
    routes = []
    while unvisited:
        route, load, current = [depot], 0, depot
        while True:
            fits = [n for n in unvisited if load + demands[n] <= capacity]
            if not fits:
                break
            nxt = min(fits, key=lambda n: dist[current][n])
            route.append(nxt)
            load += demands[nxt]
            unvisited.remove(nxt)
            current = nxt
        if len(route) == 1:
            raise ValueError("A collection point exceeds the truck capacity.")
        route.append(depot)
        routes.append(route)
    return routes


def route_distance(route, dist):
    return sum(dist[a][b] for a, b in zip(route[:-1], route[1:]))


def total_distance(routes, dist):
    return sum(route_distance(r, dist) for r in routes)


def route_load(route, demands):
    return sum(demands[n] for n in route)
