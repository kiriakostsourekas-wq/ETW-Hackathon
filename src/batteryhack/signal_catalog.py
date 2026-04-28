from __future__ import annotations

from dataclasses import dataclass


VALID_TIMING_CLASSES = {"ex_ante", "planning", "post_clearing", "actual"}
LIVE_TIMING_CLASSES = {"ex_ante", "planning"}


@dataclass(frozen=True)
class SignalCandidate:
    segment: str
    signal: str
    source: str
    url: str
    access_type: str
    timing_class: str
    resolution: str
    update_time: str
    history_depth: str
    influence: str
    feature_column: str | None
    pre_dam_score: int
    causal_score: int
    greek_specificity_score: int
    resolution_score: int
    reproducibility_score: int
    novelty_score: int

    @property
    def total_score(self) -> int:
        return (
            self.pre_dam_score
            + self.causal_score
            + self.greek_specificity_score
            + self.resolution_score
            + self.reproducibility_score
            + self.novelty_score
        )

    @property
    def live_eligible(self) -> bool:
        return self.timing_class in LIVE_TIMING_CLASSES


SIGNAL_CANDIDATES: tuple[SignalCandidate, ...] = (
    SignalCandidate(
        segment="Residual demand and RES curtailment",
        signal="Day-ahead load forecast",
        source="ADMIE/IPTO ISP1DayAheadLoadForecast",
        url="https://www.admie.gr/en/market/market-statistics/file-download-api",
        access_type="Public JSON metadata plus workbook download",
        timing_class="ex_ante",
        resolution="15-minute daily workbook",
        update_time="D-1 morning and early afternoon revisions",
        history_depth="Public historical files by date",
        influence="Higher forecast load lifts residual demand and scarcity risk.",
        feature_column="load_forecast_mw",
        pre_dam_score=5,
        causal_score=5,
        greek_specificity_score=5,
        resolution_score=5,
        reproducibility_score=5,
        novelty_score=3,
    ),
    SignalCandidate(
        segment="Residual demand and RES curtailment",
        signal="Day-ahead RES forecast",
        source="ADMIE/IPTO ISP1DayAheadRESForecast",
        url="https://www.admie.gr/en/market/market-statistics/file-download-api",
        access_type="Public JSON metadata plus workbook download",
        timing_class="ex_ante",
        resolution="15-minute daily workbook",
        update_time="D-1 morning and early afternoon revisions",
        history_depth="Public historical files by date",
        influence="High forecast RES lowers net load and raises midday zero-price risk.",
        feature_column="res_forecast_mw",
        pre_dam_score=5,
        causal_score=5,
        greek_specificity_score=5,
        resolution_score=5,
        reproducibility_score=5,
        novelty_score=3,
    ),
    SignalCandidate(
        segment="Weather and demand",
        signal="Regional weather forecast",
        source="Open-Meteo",
        url="https://open-meteo.com/en/docs",
        access_type="Open API, no token",
        timing_class="ex_ante",
        resolution="Hourly, interpolated to 15-minute",
        update_time="Continuously refreshed forecasts",
        history_depth="Forecast and historical APIs",
        influence="Temperature, cloud, wind, and radiation drive load, solar, and wind output.",
        feature_column="shortwave_radiation",
        pre_dam_score=5,
        causal_score=4,
        greek_specificity_score=4,
        resolution_score=4,
        reproducibility_score=5,
        novelty_score=3,
    ),
    SignalCandidate(
        segment="Thermal, hydro, and outage availability",
        signal="Unit availability",
        source="ADMIE/IPTO ISP1UnitAvailabilities",
        url="https://www.admie.gr/en/market/market-statistics/file-download-api",
        access_type="Public JSON metadata plus workbook download",
        timing_class="ex_ante",
        resolution="Daily workbook",
        update_time="D-1 with revisions",
        history_depth="Public historical files by date",
        influence="Lower available dispatchable capacity steepens the supply curve.",
        feature_column="dispatchable_availability_mw",
        pre_dam_score=5,
        causal_score=5,
        greek_specificity_score=5,
        resolution_score=4,
        reproducibility_score=4,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Cross-border coupling and neighboring prices",
        signal="Available transfer capacity",
        source="ADMIE/IPTO DailyAuctionsSpecificationsATC",
        url="https://www.admie.gr/en/market/market-statistics/file-download-api",
        access_type="Public JSON metadata plus workbook download",
        timing_class="ex_ante",
        resolution="Daily interconnector workbook",
        update_time="Published before delivery day",
        history_depth="Public historical files by date",
        influence="Import/export capacity changes the coupled-market clearing constraint.",
        feature_column="atc_import_export_mw",
        pre_dam_score=4,
        causal_score=4,
        greek_specificity_score=5,
        resolution_score=3,
        reproducibility_score=4,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Thermal, hydro, and outage availability",
        signal="Reservoir and water-use constraints",
        source="ADMIE/IPTO ReservoirFillingRate and WaterUsageDeclaration",
        url="https://www.admie.gr/en/market/market-statistics/file-download-api",
        access_type="Public JSON metadata plus workbook download",
        timing_class="ex_ante",
        resolution="Daily or weekly",
        update_time="Before relevant delivery period",
        history_depth="Public historical files by date",
        influence="Hydro scarcity limits flexible low-cost supply during peak hours.",
        feature_column="hydro_flexibility_index",
        pre_dam_score=4,
        causal_score=4,
        greek_specificity_score=5,
        resolution_score=3,
        reproducibility_score=4,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Gas and carbon marginal-cost stack",
        signal="Dutch TTF gas proxy",
        source="ICE Dutch TTF Natural Gas Futures",
        url="https://www.ice.com/products/27996665/Dutch-TTF-Gas-Futures/data",
        access_type="Public product page; systematic data may be licensed",
        timing_class="ex_ante",
        resolution="Daily/front-month market data",
        update_time="Trading day",
        history_depth="Depends on licensed access",
        influence="Gas-fired units often set the marginal electricity offer.",
        feature_column="ttf_gas_eur_mwh",
        pre_dam_score=4,
        causal_score=5,
        greek_specificity_score=3,
        resolution_score=2,
        reproducibility_score=2,
        novelty_score=4,
    ),
    SignalCandidate(
        segment="Gas and carbon marginal-cost stack",
        signal="EU ETS EUA carbon proxy",
        source="EEX Market Data Hub",
        url="https://www.eex.com/en/market-data/market-data-hub",
        access_type="Public web hub; systematic data may be licensed",
        timing_class="ex_ante",
        resolution="Daily market data",
        update_time="Trading day",
        history_depth="Public hub has limited history; DataSource is licensed",
        influence="Carbon cost moves gas/lignite variable costs and offers.",
        feature_column="eua_eur_tonne",
        pre_dam_score=4,
        causal_score=4,
        greek_specificity_score=2,
        resolution_score=2,
        reproducibility_score=2,
        novelty_score=4,
    ),
    SignalCandidate(
        segment="Cross-border coupling and neighboring prices",
        signal="Bulgaria day-ahead market prices",
        source="IBEX DAM prices and volumes",
        url="https://ibex.bg/markets/dam/day-ahead-prices-and-volumes-v2-0-2/",
        access_type="Public web table with CSV/XLS controls",
        timing_class="post_clearing",
        resolution="Hourly",
        update_time="After SDAC market coupling results",
        history_depth="Public recent history, site states recent-month limitation",
        influence="Bulgarian price and flows help explain Greek coupling outcomes.",
        feature_column="bg_dam_price_eur_mwh",
        pre_dam_score=2,
        causal_score=4,
        greek_specificity_score=4,
        resolution_score=3,
        reproducibility_score=3,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Cross-border coupling and neighboring prices",
        signal="Italy MGP prices and transits",
        source="GME market results",
        url="https://www.mercatoelettrico.org/en-us/Home/Results/Electricity/MGP",
        access_type="Public web/API subject to site terms",
        timing_class="post_clearing",
        resolution="Hourly",
        update_time="After Italian MGP clearing",
        history_depth="Public results and API pages",
        influence="Italy-Greece interconnector economics affect imports/exports.",
        feature_column="it_dam_price_eur_mwh",
        pre_dam_score=2,
        causal_score=4,
        greek_specificity_score=3,
        resolution_score=3,
        reproducibility_score=3,
        novelty_score=4,
    ),
    SignalCandidate(
        segment="Cross-border coupling and neighboring prices",
        signal="ENTSO-E cross-border, generation, load, and outages",
        source="ENTSO-E Transparency Platform",
        url="https://web-api.tp.entsoe.eu/api",
        access_type="Token required, no OAuth application",
        timing_class="ex_ante",
        resolution="Hourly or 15-minute depending on document type",
        update_time="Dataset-specific",
        history_depth="Broad European history through API",
        influence="Adds European system context and validates HEnEx/ADMIE signals.",
        feature_column="entsoe_system_context_index",
        pre_dam_score=4,
        causal_score=4,
        greek_specificity_score=4,
        resolution_score=4,
        reproducibility_score=4,
        novelty_score=4,
    ),
    SignalCandidate(
        segment="Market microstructure",
        signal="Aggregated sell/buy curves and MCP slope",
        source="HEnEx DAM Results and ResultsSummary",
        url="https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market",
        access_type="Public workbook download",
        timing_class="post_clearing",
        resolution="15-minute from 2025-10-01",
        update_time="D-1 after market coupling results",
        history_depth="Public files by date",
        influence="Curve slope explains price sensitivity to forecast errors.",
        feature_column="curve_slope_eur_mwh_per_mw",
        pre_dam_score=1,
        causal_score=5,
        greek_specificity_score=5,
        resolution_score=5,
        reproducibility_score=4,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Residual demand and RES curtailment",
        signal="Energy surplus and curtailment diagnostics",
        source="RAAEY energy surplus monitoring",
        url=(
            "https://www.raaey.gr/energeia/en/market-monitoring/greek-wholesale-"
            "electricity-markets/electricity-prices-statistics/"
            "estimated-energy-surplus-of-the-day-ahead-market/"
        ),
        access_type="Public monitoring page",
        timing_class="post_clearing",
        resolution="Hourly charts",
        update_time="After ENEX/IPTO schedules",
        history_depth="From Target Model implementation, per page description",
        influence="Explains negative/zero-price and curtailment regimes.",
        feature_column="energy_surplus_mw",
        pre_dam_score=1,
        causal_score=4,
        greek_specificity_score=5,
        resolution_score=3,
        reproducibility_score=3,
        novelty_score=5,
    ),
    SignalCandidate(
        segment="Weather and demand",
        signal="Greek calendar and holidays",
        source="Deterministic calendar features",
        url="https://en.wikipedia.org/wiki/Public_holidays_in_Greece",
        access_type="No API required for core weekday/weekend features",
        timing_class="ex_ante",
        resolution="Daily and 15-minute derived",
        update_time="Known before delivery",
        history_depth="Complete calendar",
        influence="Holidays and weekends change load shape and price elasticity.",
        feature_column="is_weekend",
        pre_dam_score=5,
        causal_score=3,
        greek_specificity_score=3,
        resolution_score=5,
        reproducibility_score=5,
        novelty_score=2,
    ),
)


def audit_signal_catalog(candidates: tuple[SignalCandidate, ...] = SIGNAL_CANDIDATES) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = f"{candidate.source}:{candidate.signal}"
        if key in seen:
            issues.append(f"Duplicate candidate: {key}")
        seen.add(key)
        if candidate.timing_class not in VALID_TIMING_CLASSES:
            issues.append(f"{candidate.signal} has invalid timing class {candidate.timing_class}")
        for field_name in (
            "pre_dam_score",
            "causal_score",
            "greek_specificity_score",
            "resolution_score",
            "reproducibility_score",
            "novelty_score",
        ):
            value = getattr(candidate, field_name)
            if value < 1 or value > 5:
                issues.append(f"{candidate.signal} has out-of-range {field_name}: {value}")
    return issues


def ranked_signal_candidates(live_only: bool = False) -> tuple[SignalCandidate, ...]:
    candidates = SIGNAL_CANDIDATES
    if live_only:
        candidates = tuple(candidate for candidate in candidates if candidate.live_eligible)
    return tuple(sorted(candidates, key=lambda candidate: candidate.total_score, reverse=True))


def live_feature_columns() -> tuple[str, ...]:
    return tuple(
        candidate.feature_column
        for candidate in ranked_signal_candidates(live_only=True)
        if candidate.feature_column is not None
    )
