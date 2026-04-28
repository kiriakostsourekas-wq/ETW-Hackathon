from __future__ import annotations

from batteryhack.signal_catalog import (
    LIVE_TIMING_CLASSES,
    SIGNAL_CANDIDATES,
    audit_signal_catalog,
    live_feature_columns,
    ranked_signal_candidates,
)


def test_signal_catalog_is_valid_and_scored() -> None:
    assert not audit_signal_catalog()
    assert all(6 <= candidate.total_score <= 30 for candidate in SIGNAL_CANDIDATES)


def test_live_candidates_exclude_post_clearing_and_actual_sources() -> None:
    live = ranked_signal_candidates(live_only=True)

    assert live
    assert all(candidate.timing_class in LIVE_TIMING_CLASSES for candidate in live)
    assert "load_forecast_mw" in live_feature_columns()
    assert "res_forecast_mw" in live_feature_columns()
    assert "curve_slope_eur_mwh_per_mw" not in live_feature_columns()


def test_ranked_catalog_prioritizes_core_greek_ex_ante_signals() -> None:
    top_sources = {candidate.source for candidate in ranked_signal_candidates(live_only=True)[:5]}

    assert "ADMIE/IPTO ISP1DayAheadLoadForecast" in top_sources
    assert "ADMIE/IPTO ISP1DayAheadRESForecast" in top_sources
    assert any("Open-Meteo" in source for source in top_sources)
