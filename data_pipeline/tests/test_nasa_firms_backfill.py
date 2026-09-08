import pandas as pd
import pytest

from data_pipeline.sources import nasa_firms_backfill as backfill

# west, south, east, north
INDONESIA_LIKE = (95.0, -11.0, 141.0, 6.0)
QUERY_BBOX = (90.0, -12.0, 145.0, 8.0)  # deliberately wider than the analysis region


def _row(lat, lon, acq_date, acq_time="0430", satellite="N", instrument="VIIRS"):
    return {
        "latitude": lat,
        "longitude": lon,
        "acq_date": acq_date,
        "acq_time": acq_time,
        "satellite": satellite,
        "instrument": instrument,
        "confidence": "n",
    }


def test_chunk_date_range_pages_by_five_days():
    windows = list(backfill._chunk_date_range("2019-08-01", "2019-08-12", 5))
    assert windows == [
        ("2019-08-01", "2019-08-05"),
        ("2019-08-06", "2019-08-10"),
        ("2019-08-11", "2019-08-12"),
    ]


def test_chunk_date_range_single_day():
    assert list(backfill._chunk_date_range("2019-08-01", "2019-08-01", 5)) == [("2019-08-01", "2019-08-01")]


def test_chunk_date_range_rejects_inverted_range():
    with pytest.raises(ValueError):
        list(backfill._chunk_date_range("2019-08-05", "2019-08-01", 5))


def test_fetch_historical_range_pages_without_caller_involvement(monkeypatch):
    """The acceptance-criteria shape: a >5-day request becomes one result
    set, and the caller never sees a day_range parameter."""
    calls = []

    def fake_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        calls.append((start_date, day_range))
        return pd.DataFrame([_row(-2.0, 110.0, start_date)])

    monkeypatch.setattr(backfill, "fetch_area", fake_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-12", analysis_region=INDONESIA_LIKE
    )

    assert [c[0] for c in calls] == ["2019-08-01", "2019-08-06", "2019-08-11"]
    assert all(day_range <= 5 for _, day_range in calls)
    assert len(result.observations) == 3
    assert result.failed_windows == []


def test_deduplicates_overlapping_observations(monkeypatch):
    def fake_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        # Same physical detection reported by two windows (e.g. a caller
        # re-running a window) must not double-count.
        return pd.DataFrame([_row(-2.0, 110.0, "2019-08-01"), _row(-2.0, 110.0, "2019-08-01")])

    monkeypatch.setattr(backfill, "fetch_area", fake_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-01", analysis_region=INDONESIA_LIKE
    )

    assert len(result.observations) == 1


def test_splits_analysis_region_from_external_context(monkeypatch):
    def fake_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        return pd.DataFrame(
            [
                _row(-2.0, 110.0, start_date),  # inside INDONESIA_LIKE
                _row(5.5, 143.0, start_date),  # inside QUERY_BBOX, outside INDONESIA_LIKE
            ]
        )

    monkeypatch.setattr(backfill, "fetch_area", fake_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-01", analysis_region=INDONESIA_LIKE
    )

    assert len(result.observations) == 1
    assert len(result.external_context) == 1
    assert result.observations.iloc[0]["longitude"] == 110.0
    assert result.external_context.iloc[0]["longitude"] == 143.0


def test_retries_a_failing_window_before_giving_up(monkeypatch):
    attempts = {"n": 0}

    def flaky_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return pd.DataFrame([_row(-2.0, 110.0, start_date)])

    monkeypatch.setattr(backfill, "fetch_area", flaky_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-01", analysis_region=INDONESIA_LIKE, max_retries=3
    )

    assert attempts["n"] == 3
    assert result.windows[0].status == "ok"
    assert result.windows[0].attempts == 3
    assert len(result.observations) == 1


def test_records_a_window_as_failed_without_aborting_the_backfill(monkeypatch):
    def fake_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        if start_date == "2019-08-01":
            raise ConnectionError("permanently down")
        return pd.DataFrame([_row(-2.0, 110.0, start_date)])

    monkeypatch.setattr(backfill, "fetch_area", fake_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-06", analysis_region=INDONESIA_LIKE, max_retries=2
    )

    assert len(result.failed_windows) == 1
    assert result.failed_windows[0].start_date == "2019-08-01"
    assert result.failed_windows[0].error == "permanently down"
    # The second window still succeeded -- one bad window doesn't lose the rest.
    assert len(result.observations) == 1


def test_filters_rows_outside_the_requested_range(monkeypatch):
    def fake_fetch_area(source, bbox, day_range, start_date=None, expire_after=None):
        # A window can legitimately return a row just outside the caller's
        # requested range (e.g. sensor overpass timing); it must be trimmed.
        return pd.DataFrame([_row(-2.0, 110.0, "2019-07-31"), _row(-2.0, 110.0, "2019-08-01")])

    monkeypatch.setattr(backfill, "fetch_area", fake_fetch_area)

    result = backfill.fetch_historical_range(
        bbox=QUERY_BBOX, start_date="2019-08-01", end_date="2019-08-01", analysis_region=INDONESIA_LIKE
    )

    assert len(result.observations) == 1
    assert result.observations.iloc[0]["acq_date"] == "2019-08-01"
