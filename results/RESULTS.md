# Results

- **Network:** Meknes, Morocco (3.5 km around the centre) - 6854 nodes, 19170 edges
- **Collection points:** 40 - total forecast demand 8,025 kg (with a 10% safety buffer)
- **Trucks:** 5 used of 5 available - capacity 2,000 kg each

## Forecasting (backtest on the last week)

| Model | Mean absolute percentage error |
|---|---|
| Holt-Winters (damped trend, weekly seasonality) | 7.1% |
| Seasonal naive (same weekday last week) | 8.5% |

## Routing

| Plan | Total distance |
|---|---|
| Nearest-neighbour heuristic (baseline) | 83.1 km |
| OR-Tools CVRP, guided local search | 57.3 km |

**Distance reduction vs baseline: 31.1%** (solved in 15 s)

| Truck | Stops | Load (kg) | Distance (km) |
|---|---|---|---|
| 1 | 9 | 1,889 | 15.2 |
| 2 | 9 | 1,978 | 14.9 |
| 3 | 9 | 1,964 | 12.4 |
| 4 | 12 | 1,973 | 12.2 |
| 5 | 1 | 221 | 2.6 |

Waste volumes are simulated and collection points are sampled street nodes. The baseline is a heuristic, not the city's current routes. See the README for all assumptions.

![Optimized routes](routes.png)
