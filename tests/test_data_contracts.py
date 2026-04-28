from __future__ import annotations

from datetime import date

from batteryhack.analytics import validate_market_frame
from batteryhack.synthetic import synthetic_market_day


def test_synthetic_day_has_96_complete_intervals() -> None:
    frame = synthetic_market_day(date(2026, 4, 22))
    assert len(frame) == 96
    assert not validate_market_frame(frame)
