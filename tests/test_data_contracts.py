from __future__ import annotations

from datetime import date

from batteryhack.analytics import validate_market_frame
from batteryhack.data_sources import DataSourceError, load_market_bundle
from batteryhack.synthetic import day_index, synthetic_market_day


def test_synthetic_day_has_96_complete_intervals() -> None:
    frame = synthetic_market_day(date(2026, 4, 22))
    assert len(frame) == 96
    assert not validate_market_frame(frame)


def test_optional_source_failures_do_not_become_core_warnings_or_features(monkeypatch) -> None:
    delivery_date = date(2026, 4, 22)

    def frame_with(column: str, value: float):
        frame = day_index(delivery_date)
        frame[column] = value
        return frame

    def fake_ipto_forecast(_delivery_date, _filetype, column):
        return frame_with(column, 100.0), f"fixture:{column}"

    weather = day_index(delivery_date)
    for column in ("shortwave_radiation", "cloud_cover", "temperature_2m", "wind_speed_10m"):
        weather[column] = 1.0

    def optional_missing(*_args, **_kwargs):
        raise DataSourceError("optional fixture missing")

    monkeypatch.setattr(
        "batteryhack.data_sources.fetch_henex_prices",
        lambda _delivery_date: (frame_with("dam_price_eur_mwh", 80.0), "fixture:prices"),
    )
    monkeypatch.setattr("batteryhack.data_sources.fetch_ipto_forecast", fake_ipto_forecast)
    monkeypatch.setattr(
        "batteryhack.data_sources.fetch_open_meteo_weather",
        lambda _delivery_date: (weather, "fixture:weather"),
    )
    for name in (
        "fetch_ipto_unit_availability",
        "fetch_ipto_atc",
        "fetch_ipto_long_term_nominations",
        "fetch_henex_pre_market_summary",
        "fetch_henex_posnoms",
    ):
        monkeypatch.setattr(f"batteryhack.data_sources.{name}", optional_missing)

    bundle = load_market_bundle(delivery_date)

    assert bundle.warnings == []
    assert len(bundle.optional_unavailable) == 5
    assert "premarket_gas_mw" not in bundle.frame.columns
    assert "posnom_buy_mw" not in bundle.frame.columns
    assert not validate_market_frame(bundle.frame)
