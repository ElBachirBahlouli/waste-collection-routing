"""Waste volume history and demand forecasting.

Per-point collection data is not public for Moroccan cities, so the history is
simulated with explicit assumptions:
- each point has its own base level (kg/day),
- a weekly pattern, with more waste after the weekend,
- a slight drift over time and random noise.

What transfers to real data is the method: backtest a forecaster against a
naive baseline, then use its forecast as the demand the routing must serve.
"""
import warnings

import numpy as np
import pandas as pd

# Multipliers for Monday ... Sunday.
WEEKLY_PATTERN = np.array([1.25, 1.05, 0.95, 0.95, 1.00, 0.90, 0.90])


def simulate_history(n_points, weeks=8, seed=42, start="2026-08-03"):
    """Daily waste volumes (kg) per collection point, one column per point."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, periods=weeks * 7, freq="D")
    t = np.arange(len(days))
    season = WEEKLY_PATTERN[days.dayofweek]

    data = {}
    for i in range(n_points):
        base = rng.uniform(60, 240)
        drift = rng.uniform(-0.002, 0.004)
        noise = rng.normal(0, 0.08, size=len(days))
        series = base * (1 + drift * t) * season * (1 + noise)
        data[f"P{i + 1:02d}"] = np.clip(series, 1.0, None)
    return pd.DataFrame(data, index=days)


def _holt_winters(series, horizon):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            series,
            trend="add",
            damped_trend=True,
            seasonal="mul",
            seasonal_periods=7,
            initialization_method="estimated",
        ).fit()
    return np.asarray(model.forecast(horizon), dtype=float)


def _mape(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    return float(np.mean(np.abs(actual - predicted) / actual) * 100)


def backtest(history):
    """Hold out the last week and compare Holt-Winters against the seasonal
    naive forecast (same weekday, previous week). Returns mean MAPE in %."""
    train, test = history.iloc[:-7], history.iloc[-7:]
    hw, naive = [], []
    for col in history.columns:
        actual = test[col].to_numpy()
        hw.append(_mape(actual, _holt_winters(train[col], 7)))
        naive.append(_mape(actual, train[col].iloc[-7:].to_numpy()))
    return {
        "mape_holt_winters": float(np.mean(hw)),
        "mape_seasonal_naive": float(np.mean(naive)),
    }


def forecast_next_day(history):
    """Forecast of tomorrow's volume (kg) for every collection point."""
    return {col: float(_holt_winters(history[col], 1)[0])
            for col in history.columns}
