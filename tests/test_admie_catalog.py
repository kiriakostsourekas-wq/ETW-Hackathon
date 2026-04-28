from __future__ import annotations

from batteryhack.admie_catalog import ADMIE_API_ENDPOINTS, ADMIE_RELEVANT_FILETYPES, admie_filetype_names


def test_admie_catalog_has_unique_filetypes() -> None:
    names = admie_filetype_names()
    assert len(names) == len(set(names))


def test_admie_catalog_separates_ex_ante_from_actuals() -> None:
    ex_ante = set(admie_filetype_names("ex_ante"))
    actual = set(admie_filetype_names("actual"))

    assert "ISP1DayAheadLoadForecast" in ex_ante
    assert "ISP1DayAheadRESForecast" in ex_ante
    assert "RealTimeSCADASystemLoad" in actual
    assert not ex_ante & actual


def test_admie_catalog_points_to_json_api_without_fetching_data() -> None:
    assert ADMIE_API_ENDPOINTS["filetype_catalog"].endswith("/getFiletypeInfoEN")
    assert "{date_iso}" in ADMIE_API_ENDPOINTS["files_overlapping_range"]
    assert "{filetype}" in ADMIE_API_ENDPOINTS["files_exact_coverage"]
    assert ADMIE_RELEVANT_FILETYPES
