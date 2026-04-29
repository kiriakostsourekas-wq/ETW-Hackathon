from __future__ import annotations

from datetime import date

import pandas as pd

from batteryhack.data_sources import (
    parse_henex_posnoms,
    parse_henex_pre_market_summary,
    parse_ipto_long_term_nominations,
    parse_ipto_unit_availability,
)


def test_parse_henex_pre_market_summary_extracts_96_interval_features(tmp_path):
    values = list(range(1, 97))
    rows = [
        ["Total BUY Nominations", *([None] * 96)],
        ["Greece Mainland", *values],
        ["Total SELL Nominations", *([None] * 96)],
        ["Greece Mainland", *[value + 10 for value in values]],
        ["GAS", *[100] * 96],
        ["BESS", *[2] * 96],
        ["DEMAND", *[300] * 96],
        ["BESS", *[3] * 96],
        ["TOTAL IMPORTS", *[20] * 96],
        ["TOTAL EXPORTS", *[5] * 96],
    ]
    path = tmp_path / "premarket.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False, header=False)

    parsed = parse_henex_pre_market_summary(path, date(2026, 4, 29))

    assert len(parsed) == 96
    assert parsed["premarket_gas_mw"].iloc[0] == 100
    assert parsed["premarket_bess_production_mw"].iloc[0] == 2
    assert parsed["premarket_bess_demand_mw"].iloc[0] == 3
    assert parsed["premarket_net_sell_nomination_mw"].iloc[0] == 10
    assert parsed["premarket_net_imports_mw"].iloc[0] == 15


def test_parse_henex_posnoms_aggregates_buy_sell_orders(tmp_path):
    path = tmp_path / "posnoms.xlsx"
    rows = [
        {
            "SIDE_DESCR": "Buy",
            "DELIVERY_MTU": "2026-04-29 00:00:00",
            "TOTAL_ORDERS": 4,
        },
        {
            "SIDE_DESCR": "Sell",
            "DELIVERY_MTU": "2026-04-29 00:00:00",
            "TOTAL_ORDERS": 9,
        },
    ]
    pd.DataFrame(rows).to_excel(path, index=False)

    parsed = parse_henex_posnoms(path, date(2026, 4, 29))

    assert len(parsed) == 96
    assert parsed["posnom_buy_mw"].iloc[0] == 4
    assert parsed["posnom_sell_mw"].iloc[0] == 9
    assert parsed["posnom_net_sell_mw"].iloc[0] == 5


def test_parse_ipto_unit_availability_expands_daily_scalar(tmp_path):
    path = tmp_path / "availability.xlsx"
    rows = [
        ["A/A", "Unit", "now", "for delivery"],
        [1, "UNIT_A", 80, 100],
        [2, "UNIT_B", 50, 70],
    ]
    pd.DataFrame(rows).to_excel(path, index=False, header=False)

    parsed = parse_ipto_unit_availability(path, date(2026, 4, 22))

    assert len(parsed) == 96
    assert parsed["dispatchable_availability_mw"].iloc[0] == 170


def test_parse_ipto_long_term_nominations_returns_net_import_signal(tmp_path):
    path = tmp_path / "ltptr.xlsx"
    imports = [10] * 24
    exports = [4] * 24
    rows = [
        ["IMPORTS", "Nominations", "ALBANIA", *imports],
        ["EXPORTS", "Nominations", "ALBANIA", *exports],
    ]
    pd.DataFrame(rows).to_excel(path, index=False, header=False)

    parsed = parse_ipto_long_term_nominations(path, date(2026, 4, 22))

    assert len(parsed) == 96
    assert parsed["ltptr_import_nomination_mw"].iloc[0] == 10
    assert parsed["ltptr_export_nomination_mw"].iloc[0] == 4
    assert parsed["ltptr_net_import_nomination_mw"].iloc[0] == 6
