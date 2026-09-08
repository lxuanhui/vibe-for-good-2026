import pandas as pd

from data_pipeline.clustering.firms_clustering import cluster_events


def _row(lat, lon, acq_date, acq_time=1200, frp=10.0, satellite="N", instrument="VIIRS"):
    return {
        "latitude": lat,
        "longitude": lon,
        "acq_date": acq_date,
        "acq_time": acq_time,
        "frp": frp,
        "satellite": satellite,
        "instrument": instrument,
    }


def test_nearby_same_day_detections_form_one_event():
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-09-01", 1200),
            _row(-2.501, 114.001, "2019-09-01", 1210),  # ~150m away, minutes later
        ]
    )
    events, annotated = cluster_events(obs)
    assert len(events) == 1
    assert events[0].observation_count == 2
    assert annotated["event_id"].nunique() == 1


def test_spatially_distant_detections_form_separate_events():
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-09-01"),
            _row(1.050, 101.450, "2019-09-01"),  # Riau, hundreds of km from Kalimantan
        ]
    )
    events, _ = cluster_events(obs)
    assert len(events) == 2
    assert {e.observation_count for e in events} == {1, 1}


def test_splits_temporally_disconnected_clusters_at_the_same_location():
    """Burn, go cold for 90 days, reignite at the same spot -- two
    FireEvents, not one that spans the gap."""
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-06-01"),
            _row(-2.500, 114.000, "2019-06-01", acq_time=1230),
            _row(-2.5001, 114.0001, "2019-09-01"),
            _row(-2.5001, 114.0001, "2019-09-01", acq_time=1230),
        ]
    )
    events, _ = cluster_events(obs, temporal_threshold_hours=72.0)
    assert len(events) == 2
    assert sorted(e.observation_count for e in events) == [2, 2]
    assert events[0].first_detection.startswith("2019-06-01")
    assert events[1].first_detection.startswith("2019-09-01")


def test_transitive_chain_merges_into_one_event_even_if_endpoints_are_far_apart():
    """a-b and b-c are each within threshold; a-c alone would not be. This
    is documented single-linkage chaining behaviour, not a bug."""
    obs = pd.DataFrame(
        [
            _row(-2.5000, 114.0000, "2019-09-01", 1200),
            _row(-2.5150, 114.0000, "2019-09-01", 1800),  # ~1.7km south of point 1
            _row(-2.5300, 114.0000, "2019-09-01", 2359),  # ~1.7km south of point 2, ~3.3km from point 1
        ]
    )
    events, _ = cluster_events(obs, spatial_threshold_km=2.0)
    assert len(events) == 1
    assert events[0].observation_count == 3


def test_preserves_original_observation_columns_untouched():
    obs = pd.DataFrame([_row(-2.500, 114.000, "2019-09-01"), _row(1.050, 101.450, "2019-09-01")])
    _, annotated = cluster_events(obs)
    for col in obs.columns:
        assert (annotated[col] == obs[col]).all()
    assert "event_id" in annotated.columns


def test_events_link_back_to_their_constituent_observation_indices():
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-09-01"),
            _row(-2.501, 114.001, "2019-09-01"),
            _row(1.050, 101.450, "2019-09-01"),
        ]
    )
    events, annotated = cluster_events(obs)
    for event in events:
        rows = annotated.iloc[event.observation_indices]
        assert (rows["event_id"] == event.event_id).all()
    assert sum(e.observation_count for e in events) == len(obs)


def test_computes_required_cluster_metrics():
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-09-01", 1200, frp=5.0),
            _row(-2.501, 114.001, "2019-09-02", 1200, frp=15.0),
        ]
    )
    events, _ = cluster_events(obs)
    assert len(events) == 1
    event = events[0]
    assert event.observation_count == 2
    assert event.max_frp == 15.0
    assert event.mean_frp == 10.0
    assert event.duration_hours == 24.0
    assert event.sensor_mix == ["N/VIIRS"]
    assert event.centroid[0] == (-2.500 + -2.501) / 2
    assert event.bbox == (114.000, -2.501, 114.001, -2.500)


def test_stable_event_id_is_independent_of_row_order():
    obs = pd.DataFrame(
        [
            _row(-2.500, 114.000, "2019-09-01", 1200),
            _row(-2.501, 114.001, "2019-09-01", 1210),
        ]
    )
    events_a, _ = cluster_events(obs)
    events_b, _ = cluster_events(obs.iloc[::-1].reset_index(drop=True))
    assert events_a[0].event_id == events_b[0].event_id


def test_empty_input_returns_no_events():
    obs = pd.DataFrame(columns=["latitude", "longitude", "acq_date", "acq_time", "frp"])
    events, annotated = cluster_events(obs)
    assert events == []
    assert "event_id" in annotated.columns
    assert len(annotated) == 0
