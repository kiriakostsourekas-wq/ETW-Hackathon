from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComparableProject:
    rank: int
    name: str
    url: str
    region: str
    market_scope: str
    similarity_score: int
    mental_model: str
    reusable_patterns: tuple[str, ...]
    embedded_decisions: tuple[str, ...]
    caution: str


TOP_COMPARABLE_PROJECTS: tuple[ComparableProject, ...] = (
    ComparableProject(
        rank=1,
        name="FlexPwr/bess-optimizer",
        url="https://github.com/FlexPwr/bess-optimizer",
        region="Germany / EPEX",
        market_scope="Day-ahead auction, intraday auction, intraday continuous",
        similarity_score=96,
        mental_model=(
            "Sequential market optimization over a 96-quarter BESS schedule with explicit "
            "SoC, charge, discharge, cycle, and market-position constraints."
        ),
        reusable_patterns=(
            "Use 96 interval variables and publish the mathematical constraint story.",
            "Keep day-ahead and intraday decisions separable when adding Greek IDM later.",
            "Report charge/discharge/SOC/profit arrays as first-class outputs.",
        ),
        embedded_decisions=(
            "The Greek prototype keeps 96 MTUs as the core optimization horizon.",
            "The app now documents the current model as price-taker DAM with intraday as a later layer.",
            "Sensitivity and research text distinguish implemented constraints from future market stacking.",
        ),
        caution=(
            "German DA trading historically had hourly block parity in this model; Greek DAM is now "
            "15-minute, so hourly parity constraints should not be copied."
        ),
    ),
    ComparableProject(
        rank=2,
        name="gschivley/battery_model",
        url="https://github.com/gschivley/battery_model",
        region="New York / NYISO",
        market_scope="Day-ahead LBMP arbitrage backtest",
        similarity_score=88,
        mental_model=(
            "Perfect-foresight day-ahead arbitrage over historical market prices, with battery "
            "power, energy, round-trip efficiency, daily throughput, SoC, and revenue reporting."
        ),
        reusable_patterns=(
            "Separate market-data reading, optimization, and reporting notebooks/modules.",
            "Use annual or multi-day backtests to describe revenue distribution, not only one good day.",
            "Keep daily throughput/cycle limits visible to users.",
        ),
        embedded_decisions=(
            "The METLEN UI exposes cycle budget and efficiency as first-order assumptions.",
            "The sensitivity table reports revenue, discharged MWh, equivalent cycles, and captured spread.",
            "The project keeps an oracle DAM mode for achievable-value benchmarking.",
        ),
        caution=(
            "NYISO examples are hourly and historical; Greek production runs need 15-minute prices "
            "and live-safe forecast inputs."
        ),
    ),
    ComparableProject(
        rank=3,
        name="romilandc/battery-storage-optimization-energy-ancillary",
        url="https://github.com/romilandc/battery-storage-optimization-energy-ancillary",
        region="California / CAISO",
        market_scope="Energy plus ancillary-service co-optimization",
        similarity_score=84,
        mental_model=(
            "Battery revenue maximization across energy and reserve-like products with mutually "
            "exclusive buy/sell modes, SoC dynamics, fees, and product-level P&L plots."
        ),
        reusable_patterns=(
            "Represent market products explicitly instead of hiding value stacking inside one price.",
            "Track product-level dispatch and P&L for explainability.",
            "Use public ISO data APIs as a repeatable ingestion pattern where possible.",
        ),
        embedded_decisions=(
            "The Research tab states ancillary services as future value-stacking scope.",
            "The current app keeps DAM as the implemented product to avoid unsupported Greek assumptions.",
            "The source map and docs make clear what would be required before adding reserves.",
        ),
        caution=(
            "CAISO ancillary products and nodal prices do not map directly to HEnEx DAM; this is an "
            "architecture reference, not a Greek market calibration."
        ),
    ),
)


def comparable_projects_table() -> list[dict[str, object]]:
    return [
        {
            "rank": project.rank,
            "project": project.name,
            "url": project.url,
            "region": project.region,
            "market_scope": project.market_scope,
            "similarity_score": project.similarity_score,
            "mental_model": project.mental_model,
            "what_we_can_get": " ".join(project.reusable_patterns),
        }
        for project in TOP_COMPARABLE_PROJECTS
    ]
