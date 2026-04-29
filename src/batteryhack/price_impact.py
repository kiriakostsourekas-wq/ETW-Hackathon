from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import MTU_HOURS
from .optimizer import BatteryParams, OptimizationOutput, optimize_battery_schedule


@dataclass(frozen=True)
class StorageImpactParams:
    fleet_power_mw: float = 330.0
    fleet_energy_mwh: float = 790.0
    charge_price_elasticity_eur_mwh_per_gw: float = 8.0
    discharge_price_elasticity_eur_mwh_per_gw: float = 10.0
    spread_compression_factor: float = 0.08
    reference_power_mw: float | None = None
    scenario_name: str = "Storage-aware medium impact"


@dataclass
class PriceImpactResult:
    frame: pd.DataFrame
    metrics: dict[str, float]


@dataclass
class StorageAwareSimulation:
    schedule: pd.DataFrame
    adjusted_market: pd.DataFrame
    impact_metrics: dict[str, float]
    status: str
    iterations_run: int


PRICE_IMPACT_SCENARIOS: dict[str, StorageImpactParams] = {
    "Storage-aware low impact": StorageImpactParams(
        charge_price_elasticity_eur_mwh_per_gw=4.0,
        discharge_price_elasticity_eur_mwh_per_gw=5.0,
        spread_compression_factor=0.03,
        scenario_name="Storage-aware low impact",
    ),
    "Storage-aware medium impact": StorageImpactParams(
        charge_price_elasticity_eur_mwh_per_gw=8.0,
        discharge_price_elasticity_eur_mwh_per_gw=10.0,
        spread_compression_factor=0.08,
        scenario_name="Storage-aware medium impact",
    ),
    "Storage-aware high impact": StorageImpactParams(
        charge_price_elasticity_eur_mwh_per_gw=15.0,
        discharge_price_elasticity_eur_mwh_per_gw=18.0,
        spread_compression_factor=0.16,
        scenario_name="Storage-aware high impact",
    ),
}

FLEET_SCENARIOS: dict[str, tuple[float, float]] = {
    "Only METLEN 330 MW": (330.0, 790.0),
    "First Greek standalone fleet": (1000.0, 2400.0),
    "High-storage future case": (3000.0, 7200.0),
}


def adjust_prices_for_storage_feedback(
    market: pd.DataFrame,
    schedule: pd.DataFrame,
    params: StorageImpactParams,
    price_col: str = "dam_price_eur_mwh",
    output_col: str = "storage_adjusted_price_eur_mwh",
    dt_hours: float = MTU_HOURS,
) -> PriceImpactResult:
    """Apply a transparent storage-feedback scenario to a base price series.

    The schedule is treated as the normalized behavior of the participating BESS fleet:
    charging adds demand and lifts the affected interval price, while discharging adds
    supply and suppresses the affected interval price. The spread-compression term is
    deliberately scenario-based until HEnEx curve slope parsing is available.
    """
    if price_col not in market.columns:
        raise ValueError(f"{price_col} is missing from market frame")
    if params.fleet_power_mw < 0 or params.fleet_energy_mwh < 0:
        raise ValueError("fleet_power_mw and fleet_energy_mwh must be non-negative")
    if not 0 <= params.spread_compression_factor <= 1:
        raise ValueError("spread_compression_factor must be in [0, 1]")

    frame = market.copy()
    base_prices = pd.to_numeric(frame[price_col], errors="coerce").to_numpy(float)
    if np.isnan(base_prices).any():
        raise ValueError(f"{price_col} contains missing or non-numeric values")

    charge_mw, discharge_mw = _aligned_schedule_power(market, schedule)
    if params.fleet_power_mw == 0 or params.fleet_energy_mwh == 0:
        return _unchanged_result(frame, base_prices, output_col, params)

    reference_power_mw = params.reference_power_mw
    if reference_power_mw is None:
        reference_power_mw = float(max(charge_mw.max(initial=0), discharge_mw.max(initial=0)))
    if reference_power_mw <= 1e-9 or (charge_mw + discharge_mw).sum() <= 1e-9:
        return _unchanged_result(frame, base_prices, output_col, params)

    fleet_scale = params.fleet_power_mw / reference_power_mw
    fleet_charge_mw = np.clip(charge_mw * fleet_scale, 0, params.fleet_power_mw)
    fleet_discharge_mw = np.clip(discharge_mw * fleet_scale, 0, params.fleet_power_mw)

    fleet_charged_mwh = float(fleet_charge_mw.sum() * dt_hours)
    fleet_discharged_mwh = float(fleet_discharge_mw.sum() * dt_hours)
    fleet_throughput_mwh = fleet_charged_mwh + fleet_discharged_mwh
    activity = min(fleet_throughput_mwh / max(2 * params.fleet_energy_mwh, 1e-9), 1.0)

    center_price = float(np.median(base_prices))
    compression_strength = params.spread_compression_factor * activity
    compressed_prices = center_price + (base_prices - center_price) * (1 - compression_strength)

    direct_adjustment = (
        params.charge_price_elasticity_eur_mwh_per_gw * fleet_charge_mw / 1000.0
        - params.discharge_price_elasticity_eur_mwh_per_gw * fleet_discharge_mw / 1000.0
    )
    adjusted_prices = compressed_prices + direct_adjustment

    charging = fleet_charge_mw > fleet_discharge_mw + 1e-9
    discharging = fleet_discharge_mw > fleet_charge_mw + 1e-9
    adjusted_prices[charging] = np.maximum(adjusted_prices[charging], base_prices[charging])
    adjusted_prices[discharging] = np.minimum(adjusted_prices[discharging], base_prices[discharging])

    frame[output_col] = adjusted_prices
    frame["storage_price_adjustment_eur_mwh"] = adjusted_prices - base_prices
    frame["storage_fleet_charge_mw"] = fleet_charge_mw
    frame["storage_fleet_discharge_mw"] = fleet_discharge_mw

    metrics = _impact_metrics(
        market=frame,
        base_prices=base_prices,
        adjusted_prices=adjusted_prices,
        params=params,
        fleet_charged_mwh=fleet_charged_mwh,
        fleet_discharged_mwh=fleet_discharged_mwh,
    )
    return PriceImpactResult(frame=frame, metrics=metrics)


def optimize_with_storage_feedback(
    market: pd.DataFrame,
    battery_params: BatteryParams,
    impact_params: StorageImpactParams,
    price_col: str = "dam_price_eur_mwh",
    output_col: str = "storage_adjusted_price_eur_mwh",
    iterations: int = 2,
    dt_hours: float = MTU_HOURS,
) -> StorageAwareSimulation:
    """Iterate price-taker dispatch and storage-feedback prices for scenario analysis."""
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    working = market.copy()
    working[output_col] = pd.to_numeric(working[price_col], errors="coerce").to_numpy(float)
    last_output: OptimizationOutput | None = None
    last_impact: PriceImpactResult | None = None

    for iteration in range(1, iterations + 1):
        last_output = optimize_battery_schedule(
            working,
            battery_params,
            price_col=output_col,
            dt_hours=dt_hours,
        )
        last_impact = adjust_prices_for_storage_feedback(
            market,
            last_output.schedule,
            impact_params,
            price_col=price_col,
            output_col=output_col,
            dt_hours=dt_hours,
        )
        previous_prices = working[output_col].to_numpy(float)
        next_prices = last_impact.frame[output_col].to_numpy(float)
        working = last_impact.frame.copy()
        if np.max(np.abs(next_prices - previous_prices)) < 0.01:
            break

    if last_output is None or last_impact is None:
        raise RuntimeError("storage-aware simulation did not run")

    return StorageAwareSimulation(
        schedule=last_output.schedule,
        adjusted_market=last_impact.frame,
        impact_metrics=last_impact.metrics,
        status=last_output.status,
        iterations_run=iteration,
    )


def estimate_curve_slope_from_henex(curve_frame: pd.DataFrame) -> float | None:
    """Future hook for HEnEx aggregated-curve elasticity once the schema is wired.

    The app currently uses literature-calibrated scenario elasticities. This function
    exists so curve parsing can replace those assumptions without touching the UI.
    """
    price_candidates = [col for col in curve_frame.columns if "price" in col.lower()]
    quantity_candidates = [
        col
        for col in curve_frame.columns
        if any(token in col.lower() for token in ("qty", "quantity", "volume", "mw", "mwh"))
    ]
    if not price_candidates or not quantity_candidates or len(curve_frame) < 2:
        return None

    prices = pd.to_numeric(curve_frame[price_candidates[0]], errors="coerce")
    quantities = pd.to_numeric(curve_frame[quantity_candidates[0]], errors="coerce")
    clean = pd.DataFrame({"price": prices, "quantity": quantities}).dropna().sort_values("quantity")
    if len(clean) < 2:
        return None
    quantity_span_gw = (clean["quantity"].iloc[-1] - clean["quantity"].iloc[0]) / 1000.0
    if abs(quantity_span_gw) < 1e-9:
        return None
    price_span = clean["price"].iloc[-1] - clean["price"].iloc[0]
    return float(abs(price_span / quantity_span_gw))


def _aligned_schedule_power(market: pd.DataFrame, schedule: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    required = {"charge_mw", "discharge_mw"}
    if not required.issubset(schedule.columns):
        missing = ", ".join(sorted(required - set(schedule.columns)))
        raise ValueError(f"schedule is missing required columns: {missing}")

    if "timestamp" in market.columns and "timestamp" in schedule.columns:
        aligned = market[["timestamp"]].merge(
            schedule[["timestamp", "charge_mw", "discharge_mw"]],
            on="timestamp",
            how="left",
        )
    else:
        if len(market) != len(schedule):
            raise ValueError("market and schedule must have the same length without timestamp columns")
        aligned = schedule[["charge_mw", "discharge_mw"]].copy()

    aligned = aligned.fillna({"charge_mw": 0.0, "discharge_mw": 0.0})
    charge_mw = pd.to_numeric(aligned["charge_mw"], errors="coerce").fillna(0.0).to_numpy(float)
    discharge_mw = pd.to_numeric(aligned["discharge_mw"], errors="coerce").fillna(0.0).to_numpy(float)
    return charge_mw, discharge_mw


def _unchanged_result(
    frame: pd.DataFrame,
    base_prices: np.ndarray,
    output_col: str,
    params: StorageImpactParams,
) -> PriceImpactResult:
    output = frame.copy()
    output[output_col] = base_prices
    output["storage_price_adjustment_eur_mwh"] = 0.0
    output["storage_fleet_charge_mw"] = 0.0
    output["storage_fleet_discharge_mw"] = 0.0
    return PriceImpactResult(
        frame=output,
        metrics={
            "fleet_power_mw": params.fleet_power_mw,
            "fleet_energy_mwh": params.fleet_energy_mwh,
            "fleet_charged_mwh": 0.0,
            "fleet_discharged_mwh": 0.0,
            "fleet_equivalent_cycles": 0.0,
            "avg_price_adjustment_eur_mwh": 0.0,
            "average_spread_compression_eur_mwh": 0.0,
            "spread_compression_pct": 0.0,
            "midday_price_uplift_eur_mwh": 0.0,
            "evening_peak_suppression_eur_mwh": 0.0,
        },
    )


def _impact_metrics(
    market: pd.DataFrame,
    base_prices: np.ndarray,
    adjusted_prices: np.ndarray,
    params: StorageImpactParams,
    fleet_charged_mwh: float,
    fleet_discharged_mwh: float,
) -> dict[str, float]:
    base_spread = float(np.percentile(base_prices, 90) - np.percentile(base_prices, 10))
    adjusted_spread = float(np.percentile(adjusted_prices, 90) - np.percentile(adjusted_prices, 10))
    spread_compression = max(0.0, base_spread - adjusted_spread)

    hours = _hour_of_day(market)
    midday = (hours >= 10.0) & (hours < 16.0)
    evening = (hours >= 17.0) & (hours < 22.0)
    adjustment = adjusted_prices - base_prices

    return {
        "fleet_power_mw": params.fleet_power_mw,
        "fleet_energy_mwh": params.fleet_energy_mwh,
        "fleet_charged_mwh": fleet_charged_mwh,
        "fleet_discharged_mwh": fleet_discharged_mwh,
        "fleet_equivalent_cycles": fleet_discharged_mwh / max(params.fleet_energy_mwh, 1e-9),
        "avg_price_adjustment_eur_mwh": float(np.mean(adjustment)),
        "average_spread_compression_eur_mwh": spread_compression,
        "spread_compression_pct": (
            float(spread_compression / base_spread * 100.0) if base_spread > 1e-9 else 0.0
        ),
        "midday_price_uplift_eur_mwh": _masked_mean(adjustment, midday),
        "evening_peak_suppression_eur_mwh": _masked_mean(-adjustment, evening),
    }


def _hour_of_day(frame: pd.DataFrame) -> np.ndarray:
    if "timestamp" not in frame.columns:
        return np.linspace(0, 24, len(frame), endpoint=False)
    timestamp = pd.to_datetime(frame["timestamp"])
    return (timestamp.dt.hour + timestamp.dt.minute / 60.0).to_numpy(float)


def _masked_mean(values: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    return float(np.mean(values[mask]))
