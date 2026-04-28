from __future__ import annotations

from dataclasses import dataclass

from .config import IPTO_FILE_API, IPTO_FILE_API_EXACT, IPTO_FILETYPE_INFO_URL


@dataclass(frozen=True)
class AdmieFiletype:
    filetype: str
    process: str
    data_type: str
    period_covered: str
    publication_frequency: str
    time_gate: str
    timing_class: str
    modeling_use: str


ADMIE_API_ENDPOINTS = {
    "filetype_catalog": IPTO_FILETYPE_INFO_URL,
    "files_overlapping_range": IPTO_FILE_API,
    "files_exact_coverage": IPTO_FILE_API_EXACT,
}

ADMIE_RELEVANT_FILETYPES: tuple[AdmieFiletype, ...] = (
    AdmieFiletype(
        "ISP1DayAheadLoadForecast",
        "ISP",
        "ISP Forecast",
        "DAY",
        "Daily",
        "Usually D-1 morning and early afternoon revisions",
        "ex_ante",
        "Next-day demand signal for price and dispatch forecasts.",
    ),
    AdmieFiletype(
        "ISP1DayAheadRESForecast",
        "ISP",
        "ISP Forecast",
        "DAY",
        "Daily",
        "Usually D-1 morning and early afternoon revisions",
        "ex_ante",
        "Next-day solar/wind availability and curtailment-risk signal.",
    ),
    AdmieFiletype(
        "ISP1Requirements",
        "ISP",
        "ISP Requirements",
        "DAY",
        "Daily",
        "D-1, with revisions",
        "ex_ante",
        "System requirement context before delivery.",
    ),
    AdmieFiletype(
        "ISP1UnitAvailabilities",
        "ISP",
        "Unit Availabilities",
        "DAY",
        "Daily",
        "D-1, with revisions",
        "ex_ante",
        "Thermal and hydro availability signal for marginal-price risk.",
    ),
    AdmieFiletype(
        "DailyAuctionsSpecificationsATC",
        "DAM",
        "ATC",
        "DAY",
        "Daily",
        "23:00",
        "ex_ante",
        "Import/export capacity constraints for coupled market price pressure.",
    ),
    AdmieFiletype(
        "LTPTRsNominationsSummary",
        "DAM",
        "LT PTR Nominations",
        "DAY",
        "Daily",
        "03:00",
        "ex_ante",
        "Cross-border nomination context before day-ahead clearing.",
    ),
    AdmieFiletype(
        "ReservoirFillingRate",
        "DAM",
        "Reservoir Filling Rate",
        "DAY",
        "Daily",
        "01:00",
        "ex_ante",
        "Hydro flexibility and scarcity context.",
    ),
    AdmieFiletype(
        "WeekAheadWaterUsageDeclaration",
        "DAM",
        "Water Usage Declaration",
        "WEEK",
        "Daily",
        "02:00",
        "ex_ante",
        "Hydro scheduling context for multi-day forecasts.",
    ),
    AdmieFiletype(
        "ISP1ISPResults",
        "ISP",
        "ISP Results",
        "DAY",
        "Daily",
        "After clearing",
        "post_clearing",
        "Post-clearing validation and backtest features, not ex-ante labels.",
    ),
    AdmieFiletype(
        "DispatchSchedulingResults",
        "Dispatching",
        "Dispatch Schedule",
        "DAY",
        "Daily",
        "18:00 D-1",
        "post_clearing",
        "Dispatch schedule context after market outcomes are known.",
    ),
    AdmieFiletype(
        "RealTimeSCADASystemLoad",
        "System Operation",
        "System Load",
        "DAY",
        "Daily",
        "00:00",
        "actual",
        "Actual load for backtests, calibration, and forecast-error analysis.",
    ),
    AdmieFiletype(
        "RealTimeSCADARES",
        "System Operation",
        "RES Injections",
        "DAY",
        "Daily",
        "After delivery",
        "actual",
        "Actual RES output for backtests, calibration, and curtailment analysis.",
    ),
    AdmieFiletype(
        "RealTimeSCADAImportsExports",
        "System Operation",
        "Net Interconnection Flows",
        "DAY",
        "Daily",
        "23:00",
        "actual",
        "Actual cross-border flow for backtests and price-driver attribution.",
    ),
    AdmieFiletype(
        "SystemRealizationSCADA",
        "Ex-post Market, Imbalance settlement",
        "Unit Production and System Facts",
        "DAY",
        "Daily",
        "22:00",
        "actual",
        "Realized system facts for after-the-fact analysis.",
    ),
    AdmieFiletype(
        "UnitProduction",
        "Metering, Imbalance settlement",
        "Unit Production and System Facts",
        "DAY",
        "Three times per month",
        "20:00",
        "actual",
        "Unit-level production backtest data when available.",
    ),
    AdmieFiletype(
        "UnitsMaintenanceSchedule",
        "FORWARD MARKET",
        "Unit Maintenance",
        "YEAR",
        "Yearly, on demand",
        "Annual schedule updates",
        "planning",
        "Forward outage context for structural price scenarios.",
    ),
    AdmieFiletype(
        "InterconnectionsMaintenanceSchedule",
        "FORWARD MARKET",
        "Interconnection Maintenance",
        "YEAR",
        "Yearly, on demand",
        "Annual schedule updates",
        "planning",
        "Forward cross-border outage context.",
    ),
)


def admie_filetype_names(timing_class: str | None = None) -> tuple[str, ...]:
    if timing_class is None:
        return tuple(item.filetype for item in ADMIE_RELEVANT_FILETYPES)
    return tuple(item.filetype for item in ADMIE_RELEVANT_FILETYPES if item.timing_class == timing_class)
