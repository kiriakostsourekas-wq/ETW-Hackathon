from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .config import MTU_HOURS


@dataclass(frozen=True)
class BatteryParams:
    power_mw: float = 10.0
    capacity_mwh: float = 20.0
    round_trip_efficiency: float = 0.90
    min_soc_pct: float = 10.0
    max_soc_pct: float = 90.0
    initial_soc_pct: float = 50.0
    terminal_soc_pct: float = 50.0
    degradation_cost_eur_mwh: float = 4.0
    max_cycles_per_day: float | None = None
    enforce_single_mode: bool = True


@dataclass
class OptimizationOutput:
    schedule: pd.DataFrame
    metrics: dict[str, float]
    status: str


def optimize_battery_schedule(
    market: pd.DataFrame,
    params: BatteryParams,
    price_col: str = "dam_price_eur_mwh",
    dt_hours: float = MTU_HOURS,
) -> OptimizationOutput:
    prices = pd.to_numeric(market[price_col], errors="coerce").to_numpy(dtype=float)
    if np.isnan(prices).any():
        raise ValueError(f"{price_col} contains missing or non-numeric values")
    if params.power_mw <= 0 or params.capacity_mwh <= 0:
        raise ValueError("power_mw and capacity_mwh must be positive")
    if not 0 < params.round_trip_efficiency <= 1:
        raise ValueError("round_trip_efficiency must be in (0, 1]")

    n = len(prices)
    charge_start = 0
    discharge_start = charge_start + n
    soc_start = discharge_start + n
    mode_start = soc_start + n + 1
    total_vars = mode_start + n

    charge_eff = params.round_trip_efficiency ** 0.5
    discharge_eff = params.round_trip_efficiency ** 0.5

    c = np.zeros(total_vars)
    c[charge_start:discharge_start] = (prices + params.degradation_cost_eur_mwh) * dt_hours
    c[discharge_start:soc_start] = (-prices + params.degradation_cost_eur_mwh) * dt_hours

    min_soc = params.capacity_mwh * params.min_soc_pct / 100.0
    max_soc = params.capacity_mwh * params.max_soc_pct / 100.0
    initial_soc = params.capacity_mwh * params.initial_soc_pct / 100.0
    terminal_soc = params.capacity_mwh * params.terminal_soc_pct / 100.0

    lower = np.zeros(total_vars)
    upper = np.full(total_vars, np.inf)
    upper[charge_start:discharge_start] = params.power_mw
    upper[discharge_start:soc_start] = params.power_mw
    lower[soc_start:mode_start] = min_soc
    upper[soc_start:mode_start] = max_soc
    lower[mode_start:] = 0
    upper[mode_start:] = 1

    constraints: list[LinearConstraint] = []

    equalities = lil_matrix((n + 2, total_vars))
    equality_rhs = np.zeros(n + 2)
    for t in range(n):
        equalities[t, soc_start + t + 1] = 1
        equalities[t, soc_start + t] = -1
        equalities[t, charge_start + t] = -charge_eff * dt_hours
        equalities[t, discharge_start + t] = (1 / discharge_eff) * dt_hours

    equalities[n, soc_start] = 1
    equality_rhs[n] = initial_soc
    equalities[n + 1, soc_start + n] = 1
    equality_rhs[n + 1] = terminal_soc
    constraints.append(LinearConstraint(equalities.tocsr(), equality_rhs, equality_rhs))

    if params.enforce_single_mode:
        mode_constraints = lil_matrix((2 * n, total_vars))
        lower_mode = np.full(2 * n, -np.inf)
        upper_mode = np.zeros(2 * n)
        for t in range(n):
            mode_constraints[t, charge_start + t] = 1
            mode_constraints[t, mode_start + t] = -params.power_mw
            mode_constraints[n + t, discharge_start + t] = 1
            mode_constraints[n + t, mode_start + t] = params.power_mw
            upper_mode[n + t] = params.power_mw
        constraints.append(LinearConstraint(mode_constraints.tocsr(), lower_mode, upper_mode))

    if params.max_cycles_per_day is not None:
        cycle_constraint = lil_matrix((1, total_vars))
        cycle_constraint[0, discharge_start:soc_start] = dt_hours / params.capacity_mwh
        constraints.append(
            LinearConstraint(
                cycle_constraint.tocsr(),
                -np.inf,
                float(params.max_cycles_per_day),
            )
        )

    integrality = np.zeros(total_vars)
    if params.enforce_single_mode:
        integrality[mode_start:] = 1

    result = milp(
        c=c,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"time_limit": 20, "mip_rel_gap": 1e-7},
    )
    if not result.success:
        raise RuntimeError(f"Optimization failed: {result.message}")

    values = result.x
    charge = values[charge_start:discharge_start]
    discharge = values[discharge_start:soc_start]
    soc = values[soc_start:mode_start]

    schedule = market[["timestamp", "interval", price_col]].copy()
    schedule["charge_mw"] = np.where(charge < 1e-6, 0, charge)
    schedule["discharge_mw"] = np.where(discharge < 1e-6, 0, discharge)
    schedule["net_power_mw"] = schedule["discharge_mw"] - schedule["charge_mw"]
    schedule["soc_mwh_start"] = soc[:-1]
    schedule["soc_mwh_end"] = soc[1:]
    schedule["soc_pct_end"] = schedule["soc_mwh_end"] / params.capacity_mwh * 100.0
    schedule["gross_revenue_eur"] = prices * (discharge - charge) * dt_hours
    schedule["degradation_cost_eur"] = params.degradation_cost_eur_mwh * (charge + discharge) * dt_hours
    schedule["net_revenue_eur"] = schedule["gross_revenue_eur"] - schedule["degradation_cost_eur"]
    schedule["action"] = np.select(
        [schedule["charge_mw"] > 1e-5, schedule["discharge_mw"] > 1e-5],
        ["Charge", "Discharge"],
        default="Idle",
    )

    charged_mwh = float(schedule["charge_mw"].sum() * dt_hours)
    discharged_mwh = float(schedule["discharge_mw"].sum() * dt_hours)
    avg_charge_price = (
        float((prices * charge * dt_hours).sum() / charged_mwh) if charged_mwh > 1e-9 else 0.0
    )
    avg_discharge_price = (
        float((prices * discharge * dt_hours).sum() / discharged_mwh) if discharged_mwh > 1e-9 else 0.0
    )
    metrics = {
        "gross_revenue_eur": float(schedule["gross_revenue_eur"].sum()),
        "degradation_cost_eur": float(schedule["degradation_cost_eur"].sum()),
        "net_revenue_eur": float(schedule["net_revenue_eur"].sum()),
        "charged_mwh": charged_mwh,
        "discharged_mwh": discharged_mwh,
        "equivalent_cycles": discharged_mwh / params.capacity_mwh,
        "avg_charge_price_eur_mwh": avg_charge_price,
        "avg_discharge_price_eur_mwh": avg_discharge_price,
        "captured_spread_eur_mwh": avg_discharge_price - avg_charge_price,
    }
    return OptimizationOutput(schedule=schedule, metrics=metrics, status=str(result.message))
