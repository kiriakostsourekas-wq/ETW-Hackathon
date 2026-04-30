from __future__ import annotations

import pandas as pd

from .config import MTU_HOURS


def validate_market_frame(frame: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    if len(frame) != 96:
        issues.append(f"Expected 96 MTUs, found {len(frame)}")
    required = ["timestamp", "dam_price_eur_mwh", "load_forecast_mw", "res_forecast_mw"]
    for column in required:
        if column not in frame.columns:
            issues.append(f"Missing column: {column}")
        elif frame[column].isna().any():
            issues.append(f"Column has missing values: {column}")
    if "timestamp" in frame.columns and frame["timestamp"].duplicated().any():
        issues.append("Duplicate timestamps found")
    return issues


def heuristic_threshold_schedule(frame: pd.DataFrame, power_mw: float, capacity_mwh: float) -> dict[str, float]:
    """Simple heuristic baseline: charge low quartile, discharge high quartile."""
    prices = frame["dam_price_eur_mwh"]
    low = prices.quantile(0.25)
    high = prices.quantile(0.75)
    soc = 0.5 * capacity_mwh
    min_soc = 0.1 * capacity_mwh
    max_soc = 0.9 * capacity_mwh
    gross = 0.0
    discharged_mwh = 0.0
    charged_mwh = 0.0
    for price in prices:
        if price <= low and soc < max_soc:
            energy = min(power_mw * MTU_HOURS, max_soc - soc)
            soc += energy
            gross -= energy * price
            charged_mwh += energy
        elif price >= high and soc > min_soc:
            energy = min(power_mw * MTU_HOURS, soc - min_soc)
            soc -= energy
            gross += energy * price
            discharged_mwh += energy
    return {
        "heuristic_gross_revenue_eur": gross,
        "heuristic_charged_mwh": charged_mwh,
        "heuristic_discharged_mwh": discharged_mwh,
    }


def action_windows(schedule: pd.DataFrame) -> pd.DataFrame:
    active = schedule[schedule["action"] != "Idle"].copy()
    if active.empty:
        return pd.DataFrame(columns=["action", "start", "end", "energy_mwh", "avg_price"])
    active["group"] = (active["action"] != active["action"].shift()).cumsum()
    rows = []
    for _, group in active.groupby("group"):
        action = group["action"].iloc[0]
        power_col = "charge_mw" if action == "Charge" else "discharge_mw"
        energy = group[power_col].sum() * MTU_HOURS
        weighted_price = (group["dam_price_eur_mwh"] * group[power_col]).sum()
        avg_price = weighted_price / group[power_col].sum() if group[power_col].sum() else 0
        rows.append(
            {
                "action": action,
                "start": group["timestamp"].iloc[0],
                "end": group["timestamp"].iloc[-1] + pd.Timedelta(minutes=15),
                "energy_mwh": energy,
                "avg_price": avg_price,
            }
        )
    return pd.DataFrame(rows)
