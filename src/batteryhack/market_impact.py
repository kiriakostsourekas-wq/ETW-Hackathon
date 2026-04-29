from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import MTU_HOURS
from .optimizer import BatteryParams


@dataclass(frozen=True)
class MarketImpactThresholds:
    median_abs_shift_eur_mwh: float = 0.5
    revenue_haircut_pct: float = 2.0
    minimum_valid_interval_share: float = 0.8
    local_material_p95_eur_mwh: float = 2.0
    baseline_price_tolerance_eur_mwh: float = 1.0


@dataclass(frozen=True)
class MarketImpactResult:
    interval_impacts: pd.DataFrame
    daily_summary: pd.DataFrame
    thresholds: MarketImpactThresholds


def run_single_bess_market_impact(
    market: pd.DataFrame,
    schedule: pd.DataFrame,
    curves: pd.DataFrame | dict[int, pd.DataFrame],
    battery_params: BatteryParams,
    thresholds: MarketImpactThresholds | None = None,
    price_col: str = "dam_price_eur_mwh",
    dt_hours: float = MTU_HOURS,
) -> MarketImpactResult:
    """Test whether a fixed price-taker BESS schedule would move DAM MCP.

    The schedule is not re-optimized. Each active interval is re-cleared against the
    supplied HEnEx aggregated buy/sell curve after adding the BESS action:
    charge MW shifts demand up, discharge MW shifts supply up.
    """
    thresholds = thresholds or MarketImpactThresholds()
    aligned = _align_market_and_schedule(market, schedule, price_col)
    rows: list[dict[str, Any]] = []

    for row in aligned.itertuples(index=False):
        interval = int(row.interval)
        charge_mw = float(row.charge_mw)
        discharge_mw = float(row.discharge_mw)
        base_price = float(getattr(row, price_col))
        curve = _curve_for_interval(curves, interval)
        impact = counterfactual_interval_price(
            curve,
            base_price_eur_mwh=base_price,
            charge_mw=charge_mw,
            discharge_mw=discharge_mw,
            thresholds=thresholds,
        )
        shifted_price = impact["counterfactual_price_eur_mwh"]
        row_prices = base_price if shifted_price is None else float(shifted_price)
        base_net = _interval_net_revenue(base_price, charge_mw, discharge_mw, battery_params, dt_hours)
        impacted_net = _interval_net_revenue(row_prices, charge_mw, discharge_mw, battery_params, dt_hours)
        load_mw = _maybe_float(getattr(row, "load_forecast_mw", None))
        cleared_mw = _maybe_float(getattr(row, "cleared_volume_mw", None))
        battery_abs_mw = max(charge_mw, discharge_mw)
        delivery_date = _delivery_date(row)

        rows.append(
            {
                "delivery_date": delivery_date,
                "timestamp": getattr(row, "timestamp", None),
                "interval": interval,
                "base_price_eur_mwh": base_price,
                "load_forecast_mw": load_mw,
                "cleared_volume_mw": cleared_mw,
                "charge_mw": charge_mw,
                "discharge_mw": discharge_mw,
                "battery_abs_mw": battery_abs_mw,
                "market_action": _market_action(charge_mw, discharge_mw),
                "counterfactual_price_eur_mwh": shifted_price,
                "mcp_shift_eur_mwh": impact["mcp_shift_eur_mwh"],
                "abs_mcp_shift_eur_mwh": (
                    abs(float(impact["mcp_shift_eur_mwh"]))
                    if impact["mcp_shift_eur_mwh"] is not None
                    else None
                ),
                "baseline_reclear_price_eur_mwh": impact["baseline_reclear_price_eur_mwh"],
                "baseline_reclear_error_eur_mwh": impact["baseline_reclear_error_eur_mwh"],
                "baseline_reclear_valid": impact["baseline_reclear_valid"],
                "counterfactual_reclear_valid": impact["counterfactual_reclear_valid"],
                "headline_valid": impact["headline_valid"],
                "method": impact["method"],
                "market_depth_mw_per_eur_mwh": impact["market_depth_mw_per_eur_mwh"],
                "base_net_revenue_eur": base_net,
                "impacted_net_revenue_eur": impacted_net,
                "revenue_delta_eur": impacted_net - base_net,
                "bess_power_pct_of_load": (
                    battery_abs_mw / load_mw * 100.0 if load_mw and load_mw > 0 else None
                ),
                "bess_power_pct_of_cleared_volume": (
                    battery_abs_mw / cleared_mw * 100.0 if cleared_mw and cleared_mw > 0 else None
                ),
            }
        )

    interval_impacts = pd.DataFrame(rows)
    daily_summary = _daily_summary(interval_impacts, thresholds, dt_hours)
    return MarketImpactResult(
        interval_impacts=interval_impacts,
        daily_summary=daily_summary,
        thresholds=thresholds,
    )


def counterfactual_interval_price(
    curve_frame: pd.DataFrame | None,
    base_price_eur_mwh: float,
    charge_mw: float = 0.0,
    discharge_mw: float = 0.0,
    thresholds: MarketImpactThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or MarketImpactThresholds()
    action_mw = max(charge_mw, discharge_mw)
    if action_mw <= 1e-9:
        return {
            "counterfactual_price_eur_mwh": base_price_eur_mwh,
            "mcp_shift_eur_mwh": 0.0,
            "baseline_reclear_price_eur_mwh": None,
            "baseline_reclear_error_eur_mwh": None,
            "baseline_reclear_valid": True,
            "counterfactual_reclear_valid": True,
            "headline_valid": True,
            "method": "inactive",
            "market_depth_mw_per_eur_mwh": None,
        }

    if curve_frame is None or curve_frame.empty:
        return _invalid_impact("missing_curve")

    curve = normalize_curve_frame(curve_frame)
    if curve.empty:
        return _invalid_impact("invalid_curve_schema")

    baseline_price = reclear_curve(curve)
    depth = estimate_market_depth(curve, base_price_eur_mwh)
    baseline_error = (
        abs(baseline_price - base_price_eur_mwh) if baseline_price is not None else None
    )
    baseline_valid = (
        baseline_error is not None
        and baseline_error <= thresholds.baseline_price_tolerance_eur_mwh
    )

    shifted_curve = curve.copy()
    shifted_curve["buy_mw"] = shifted_curve["buy_mw"] + max(charge_mw, 0.0)
    shifted_curve["sell_mw"] = shifted_curve["sell_mw"] + max(discharge_mw, 0.0)
    counterfactual_price = reclear_curve(shifted_curve)
    counterfactual_valid = counterfactual_price is not None
    method = "curve_reclear"

    if not baseline_valid or counterfactual_price is None:
        if depth is not None and depth > 1e-9:
            counterfactual_price = base_price_eur_mwh + (charge_mw - discharge_mw) / depth
            method = (
                "baseline_failed_local_depth_fallback"
                if not baseline_valid
                else "local_depth_fallback"
            )
        else:
            return {
                **_invalid_impact("reclear_failed"),
                "baseline_reclear_price_eur_mwh": baseline_price,
                "baseline_reclear_error_eur_mwh": baseline_error,
                "baseline_reclear_valid": bool(baseline_valid),
                "market_depth_mw_per_eur_mwh": depth,
            }

    counterfactual_price = _enforce_price_move_direction(
        base_price_eur_mwh,
        float(counterfactual_price),
        charge_mw,
        discharge_mw,
    )
    shift = counterfactual_price - base_price_eur_mwh

    return {
        "counterfactual_price_eur_mwh": counterfactual_price,
        "mcp_shift_eur_mwh": shift,
        "baseline_reclear_price_eur_mwh": baseline_price,
        "baseline_reclear_error_eur_mwh": baseline_error,
        "baseline_reclear_valid": bool(baseline_valid),
        "counterfactual_reclear_valid": bool(counterfactual_valid),
        "headline_valid": bool(baseline_valid and counterfactual_valid),
        "method": method,
        "market_depth_mw_per_eur_mwh": depth,
    }


def normalize_curve_frame(curve_frame: pd.DataFrame) -> pd.DataFrame:
    """Return normalized aggregated curve columns: price, buy MW, sell MW."""
    if curve_frame.empty:
        return pd.DataFrame(columns=["price_eur_mwh", "buy_mw", "sell_mw"])

    frame = curve_frame.copy()
    frame.columns = [str(col).strip() for col in frame.columns]
    lower = {_normalize_name(col): col for col in frame.columns}

    if {"price_eur_mwh", "buy_mw", "sell_mw"}.issubset(lower):
        normalized = frame[[lower["price_eur_mwh"], lower["buy_mw"], lower["sell_mw"]]].copy()
        normalized.columns = ["price_eur_mwh", "buy_mw", "sell_mw"]
        return _clean_curve(normalized)

    side_col = _find_column(frame, ("side", "direction", "curve", "type"))
    price_col = _find_price_column(frame)
    quantity_col = _find_quantity_column(frame)
    if side_col and price_col and quantity_col:
        tidy = frame[[side_col, price_col, quantity_col]].copy()
        tidy.columns = ["side", "price_eur_mwh", "quantity_mw"]
        tidy["side_norm"] = tidy["side"].astype(str).str.lower()
        tidy["curve_side"] = np.select(
            [
                tidy["side_norm"].str.contains("buy|demand|purchase|bid", regex=True),
                tidy["side_norm"].str.contains("sell|supply|offer|ask", regex=True),
            ],
            ["buy_mw", "sell_mw"],
            default=None,
        )
        tidy = tidy.dropna(subset=["curve_side"])
        if not tidy.empty:
            pivot = tidy.pivot_table(
                index="price_eur_mwh",
                columns="curve_side",
                values="quantity_mw",
                aggfunc="sum",
            ).reset_index()
            if {"buy_mw", "sell_mw"}.issubset(pivot.columns):
                return _clean_curve(pivot)

    buy_col = _find_column(frame, ("buy", "demand", "purchase", "bid"))
    sell_col = _find_column(frame, ("sell", "supply", "offer", "ask"))
    if price_col and buy_col and sell_col:
        normalized = frame[[price_col, buy_col, sell_col]].copy()
        normalized.columns = ["price_eur_mwh", "buy_mw", "sell_mw"]
        return _clean_curve(normalized)

    return pd.DataFrame(columns=["price_eur_mwh", "buy_mw", "sell_mw"])


def reclear_curve(curve_frame: pd.DataFrame) -> float | None:
    curve = normalize_curve_frame(curve_frame)
    if len(curve) < 2:
        return None
    curve = curve.sort_values("price_eur_mwh").reset_index(drop=True)
    prices = curve["price_eur_mwh"].to_numpy(float)
    net_supply = (curve["sell_mw"] - curve["buy_mw"]).to_numpy(float)

    exact = np.where(np.isclose(net_supply, 0.0, atol=1e-9))[0]
    if len(exact):
        return float(prices[exact[0]])

    sign_changes = np.where(np.signbit(net_supply[:-1]) != np.signbit(net_supply[1:]))[0]
    if not len(sign_changes):
        return None

    idx = int(sign_changes[0])
    x0, x1 = prices[idx], prices[idx + 1]
    y0, y1 = net_supply[idx], net_supply[idx + 1]
    if abs(y1 - y0) < 1e-12:
        return float(x0)
    return float(x0 - y0 * (x1 - x0) / (y1 - y0))


def estimate_market_depth(
    curve_frame: pd.DataFrame,
    base_price_eur_mwh: float,
    window_eur_mwh: float = 5.0,
) -> float | None:
    curve = normalize_curve_frame(curve_frame)
    if len(curve) < 2:
        return None
    curve = curve.sort_values("price_eur_mwh")
    near = curve[
        (curve["price_eur_mwh"] >= base_price_eur_mwh - window_eur_mwh)
        & (curve["price_eur_mwh"] <= base_price_eur_mwh + window_eur_mwh)
    ].copy()
    if len(near) < 2:
        nearest = (
            (curve["price_eur_mwh"] - base_price_eur_mwh)
            .abs()
            .sort_values()
            .head(min(5, len(curve)))
            .index
        )
        near = curve.loc[nearest].copy().sort_values("price_eur_mwh")
    if len(near) < 2:
        return None

    prices = near["price_eur_mwh"].to_numpy(float)
    net_supply = (near["sell_mw"] - near["buy_mw"]).to_numpy(float)
    slope, _intercept = np.polyfit(prices, net_supply, deg=1)
    slope = abs(float(slope))
    return slope if np.isfinite(slope) and slope > 1e-9 else None


def parse_henex_aggregated_curve_workbook(path: str | Path) -> pd.DataFrame:
    """Best-effort parser for HEnEx EL-DAM_AggrCurves_EN workbooks.

    The parser accepts either a workbook with one interval per sheet or a sheet that
    already contains interval, price, buy, and sell columns. Rows that cannot be
    normalized are skipped and should be counted as invalid by the experiment.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        return _normalize_curve_file_table(frame)

    workbook = pd.ExcelFile(path)
    frames: list[pd.DataFrame] = []
    for sheet_index, sheet_name in enumerate(workbook.sheet_names, start=1):
        parsed = _parse_curve_sheet(workbook, sheet_name, default_interval=sheet_index)
        if not parsed.empty:
            frames.append(parsed)
    if not frames:
        return pd.DataFrame(columns=["interval", "price_eur_mwh", "buy_mw", "sell_mw"])
    return pd.concat(frames, ignore_index=True)


def load_curve_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _normalize_curve_file_table(pd.read_csv(path))
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return parse_henex_aggregated_curve_workbook(path)
    raise ValueError(f"Unsupported curve file: {path}")


def thresholds_to_dict(thresholds: MarketImpactThresholds) -> dict[str, float]:
    return asdict(thresholds)


def _daily_summary(
    intervals: pd.DataFrame,
    thresholds: MarketImpactThresholds,
    dt_hours: float,
) -> pd.DataFrame:
    summaries: list[dict[str, Any]] = []
    for delivery_date, day in intervals.groupby("delivery_date", dropna=False):
        active = day[day["battery_abs_mw"] > 1e-6]
        denominator = len(active) if not active.empty else len(day)
        valid_base = active if not active.empty else day
        valid = valid_base[valid_base["headline_valid"].astype(bool)]
        valid_share = len(valid) / denominator if denominator else 0.0

        shifts = pd.to_numeric(valid["mcp_shift_eur_mwh"], errors="coerce").dropna()
        abs_shifts = shifts.abs()
        base_net = float(pd.to_numeric(day["base_net_revenue_eur"], errors="coerce").sum())
        impacted_net = float(pd.to_numeric(day["impacted_net_revenue_eur"], errors="coerce").sum())
        haircut = (
            max(0.0, (base_net - impacted_net) / abs(base_net) * 100.0)
            if abs(base_net) > 1e-9
            else 0.0
        )
        total_bess_volume_mwh = float(
            (pd.to_numeric(day["charge_mw"], errors="coerce").fillna(0.0).sum()
             + pd.to_numeric(day["discharge_mw"], errors="coerce").fillna(0.0).sum())
            * dt_hours
        )
        load_proxy_mwh = None
        if "bess_power_pct_of_load" in day:
            load_col = _extract_numeric(day, "load_forecast_mw")
            if load_col is not None and load_col.sum() > 0:
                load_proxy_mwh = float(load_col.sum() * dt_hours)

        median_shift = _series_quantile(abs_shifts, 0.5)
        p95_shift = _series_quantile(abs_shifts, 0.95)
        decision = _impact_decision(
            valid_share=valid_share,
            median_abs_shift=median_shift,
            p95_abs_shift=p95_shift,
            revenue_haircut_pct=haircut,
            thresholds=thresholds,
        )

        summaries.append(
            {
                "delivery_date": delivery_date,
                "intervals_total": int(len(day)),
                "active_intervals": int(len(active)),
                "headline_valid_intervals": int(len(valid)),
                "valid_interval_share": valid_share,
                "invalid_or_missing_intervals": int(denominator - len(valid)),
                "median_abs_mcp_shift_eur_mwh": median_shift,
                "p95_abs_mcp_shift_eur_mwh": p95_shift,
                "max_abs_mcp_shift_eur_mwh": _series_max(abs_shifts),
                "charge_interval_avg_uplift_eur_mwh": _series_mean(
                    valid.loc[valid["market_action"] == "charge", "mcp_shift_eur_mwh"]
                ),
                "discharge_interval_avg_suppression_eur_mwh": _series_mean(
                    valid.loc[valid["market_action"] == "discharge", "mcp_shift_eur_mwh"]
                ),
                "price_taker_net_revenue_eur": base_net,
                "impacted_net_revenue_eur": impacted_net,
                "revenue_haircut_pct": haircut,
                "total_bess_volume_mwh": total_bess_volume_mwh,
                "bess_volume_pct_of_daily_load_mwh_proxy": (
                    total_bess_volume_mwh / load_proxy_mwh * 100.0
                    if load_proxy_mwh and load_proxy_mwh > 0
                    else None
                ),
                "max_bess_power_pct_of_load": _series_max(day["bess_power_pct_of_load"]),
                "median_market_depth_mw_per_eur_mwh": _series_median(
                    day["market_depth_mw_per_eur_mwh"]
                ),
                "passes_negligible_threshold": decision == "negligible",
                "decision": decision,
            }
        )
    return pd.DataFrame(summaries)


def _impact_decision(
    valid_share: float,
    median_abs_shift: float | None,
    p95_abs_shift: float | None,
    revenue_haircut_pct: float,
    thresholds: MarketImpactThresholds,
) -> str:
    if valid_share < thresholds.minimum_valid_interval_share:
        return "inconclusive"
    if median_abs_shift is None:
        return "inconclusive"
    median_pass = median_abs_shift < thresholds.median_abs_shift_eur_mwh
    haircut_pass = revenue_haircut_pct < thresholds.revenue_haircut_pct
    if median_pass and haircut_pass:
        if (
            p95_abs_shift is not None
            and p95_abs_shift >= thresholds.local_material_p95_eur_mwh
        ):
            return "locally_material"
        return "negligible"
    return "material"


def _align_market_and_schedule(
    market: pd.DataFrame,
    schedule: pd.DataFrame,
    price_col: str,
) -> pd.DataFrame:
    required_market = {"timestamp", "interval", price_col}
    required_schedule = {"timestamp", "charge_mw", "discharge_mw"}
    if not required_market.issubset(market.columns):
        missing = ", ".join(sorted(required_market - set(market.columns)))
        raise ValueError(f"market is missing required columns: {missing}")
    if not required_schedule.issubset(schedule.columns):
        missing = ", ".join(sorted(required_schedule - set(schedule.columns)))
        raise ValueError(f"schedule is missing required columns: {missing}")

    market_cols = [
        col
        for col in [
            "timestamp",
            "interval",
            price_col,
            "load_forecast_mw",
            "cleared_volume_mw",
        ]
        if col in market.columns
    ]
    aligned = market[market_cols].merge(
        schedule[["timestamp", "charge_mw", "discharge_mw"]],
        on="timestamp",
        how="left",
    )
    aligned[["charge_mw", "discharge_mw"]] = aligned[
        ["charge_mw", "discharge_mw"]
    ].fillna(0.0)
    return aligned


def _curve_for_interval(
    curves: pd.DataFrame | dict[int, pd.DataFrame],
    interval: int,
) -> pd.DataFrame | None:
    if isinstance(curves, dict):
        return curves.get(interval)
    if curves.empty:
        return None
    interval_col = _find_column(curves, ("interval", "mtu", "period", "position"))
    if interval_col is None:
        return curves
    subset = curves[pd.to_numeric(curves[interval_col], errors="coerce") == interval]
    return subset if not subset.empty else None


def _parse_curve_sheet(
    workbook: pd.ExcelFile,
    sheet_name: str,
    default_interval: int,
) -> pd.DataFrame:
    for header_row in range(0, 8):
        try:
            frame = workbook.parse(sheet_name=sheet_name, header=header_row)
        except ValueError:
            continue
        normalized = _normalize_curve_file_table(frame, default_interval=default_interval)
        if not normalized.empty:
            return normalized
    return pd.DataFrame(columns=["interval", "price_eur_mwh", "buy_mw", "sell_mw"])


def _normalize_curve_file_table(
    frame: pd.DataFrame,
    default_interval: int | None = None,
) -> pd.DataFrame:
    interval_col = _find_column(frame, ("interval", "mtu", "period", "position"))
    if interval_col is not None:
        frames: list[pd.DataFrame] = []
        intervals = pd.to_numeric(frame[interval_col], errors="coerce")
        for interval, group in frame.assign(_interval=intervals).dropna(subset=["_interval"]).groupby(
            "_interval"
        ):
            normalized_group = normalize_curve_frame(group.drop(columns=["_interval"]))
            if normalized_group.empty:
                continue
            normalized_group["interval"] = int(interval)
            frames.append(normalized_group)
        if not frames:
            return pd.DataFrame(columns=["interval", "price_eur_mwh", "buy_mw", "sell_mw"])
        normalized = pd.concat(frames, ignore_index=True)
    else:
        normalized = normalize_curve_frame(frame)
        if normalized.empty:
            return pd.DataFrame(columns=["interval", "price_eur_mwh", "buy_mw", "sell_mw"])
        normalized["interval"] = default_interval

    normalized = normalized.dropna(subset=["interval"])
    normalized["interval"] = normalized["interval"].astype(int)
    return normalized[["interval", "price_eur_mwh", "buy_mw", "sell_mw"]]


def _clean_curve(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame[["price_eur_mwh", "buy_mw", "sell_mw"]].copy()
    for column in output.columns:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna().groupby("price_eur_mwh", as_index=False).agg(
        {"buy_mw": "mean", "sell_mw": "mean"}
    )
    return output.sort_values("price_eur_mwh").reset_index(drop=True)


def _find_price_column(frame: pd.DataFrame) -> str | None:
    return _find_column(frame, ("price", "eur", "€/mwh", "eur/mwh", "mcp"))


def _find_quantity_column(frame: pd.DataFrame) -> str | None:
    return _find_column(frame, ("quantity", "volume", "qty", "mw", "mwh"))


def _find_column(frame: pd.DataFrame, tokens: tuple[str, ...]) -> str | None:
    for column in frame.columns:
        normalized = _normalize_name(column)
        if any(token in normalized for token in tokens):
            return str(column)
    return None


def _normalize_name(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def _interval_net_revenue(
    price_eur_mwh: float,
    charge_mw: float,
    discharge_mw: float,
    params: BatteryParams,
    dt_hours: float,
) -> float:
    gross = price_eur_mwh * (discharge_mw - charge_mw) * dt_hours
    degradation = params.degradation_cost_eur_mwh * (charge_mw + discharge_mw) * dt_hours
    return float(gross - degradation)


def _market_action(charge_mw: float, discharge_mw: float) -> str:
    if charge_mw > discharge_mw + 1e-9:
        return "charge"
    if discharge_mw > charge_mw + 1e-9:
        return "discharge"
    return "idle"


def _enforce_price_move_direction(
    base_price: float,
    counterfactual_price: float,
    charge_mw: float,
    discharge_mw: float,
) -> float:
    if charge_mw > discharge_mw + 1e-9:
        return max(counterfactual_price, base_price)
    if discharge_mw > charge_mw + 1e-9:
        return min(counterfactual_price, base_price)
    return counterfactual_price


def _invalid_impact(method: str) -> dict[str, Any]:
    return {
        "counterfactual_price_eur_mwh": None,
        "mcp_shift_eur_mwh": None,
        "baseline_reclear_price_eur_mwh": None,
        "baseline_reclear_error_eur_mwh": None,
        "baseline_reclear_valid": False,
        "counterfactual_reclear_valid": False,
        "headline_valid": False,
        "method": method,
        "market_depth_mw_per_eur_mwh": None,
    }


def _maybe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _delivery_date(row: Any) -> str:
    timestamp = getattr(row, "timestamp", None)
    if timestamp is None or pd.isna(timestamp):
        return "unknown"
    return pd.Timestamp(timestamp).date().isoformat()


def _extract_numeric(frame: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in frame:
        return None
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _series_mean(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.mean()) if not clean.empty else None


def _series_median(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.median()) if not clean.empty else None


def _series_quantile(series: pd.Series, q: float) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.quantile(q)) if not clean.empty else None


def _series_max(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.max()) if not clean.empty else None
