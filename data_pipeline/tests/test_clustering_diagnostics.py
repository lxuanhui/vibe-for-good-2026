"""Clustering parameters, link diagnostics, lobes and the threshold sweep.

The synthetic set is built so each threshold has one thing it can merge:
two same-day groups 3 km apart (only a wider radius joins them), and a
reburn at the first group's location ten days later (only a longer window
joins it). What the diagnostics report for that set is therefore known in
advance, not read back from the code under test.
"""

from __future__ import annotations

import json
from itertools import chain

import pandas as pd
import pytest

from data_pipeline.clustering.diagnostics import (
    diagnose,
    format_summary,
    summarize_large_event,
    threshold_sweep,
    window,
)
from data_pipeline.clustering.firms_clustering import (
    ALGORITHM_VERSION,
    DEFAULT_SPATIAL_THRESHOLD_KM,
    DEFAULT_TEMPORAL_THRESHOLD_HOURS,
    MAX_SPATIAL_THRESHOLD_KM,
    MAX_TEMPORAL_THRESHOLD_HOURS,
    ClusteringParameters,
    cluster_events,
    cluster_run,
    event_lobes,
    resolve_parameters,
)

# 0.009 degrees of latitude is ~1.0 km; 0.027 is ~3.0 km.
KM = 0.009


def _row(lat, lon, acq_date, acq_time=1200, frp=10.0):
    return {"latitude": lat, "longitude": lon, "acq_date": acq_date, "acq_time": acq_time, "frp": frp}


def _controlled_set() -> pd.DataFrame:
    group_a = [_row(-2.5 + i * 0.001, 114.0, "2019-09-01", 1200 + i, frp=5.0 + i) for i in range(5)]
    group_b = [_row(-2.5 + 3 * KM + i * 0.001, 114.0, "2019-09-01", 1300 + i, frp=20.0) for i in range(3)]
    reburn = [_row(-2.5, 114.0, "2019-09-11", 1200), _row(-2.5 - 0.002, 114.0, "2019-09-11", 1210)]
    return pd.DataFrame(group_a + group_b + reburn)


# --- parameters ----------------------------------------------------------


def test_defaults_are_the_documented_values_and_deterministic():
    first, second = ClusteringParameters(), ClusteringParameters()
    assert first == second
    assert first.spatial_threshold_km == DEFAULT_SPATIAL_THRESHOLD_KM == 2.0
    assert first.temporal_threshold_hours == DEFAULT_TEMPORAL_THRESHOLD_HOURS == 72.0
    assert first.is_default
    assert first.to_dict()["algorithm_version"] == ALGORITHM_VERSION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spatial_threshold_km", 0),
        ("spatial_threshold_km", -1.0),
        ("spatial_threshold_km", float("nan")),
        ("spatial_threshold_km", float("inf")),
        ("spatial_threshold_km", MAX_SPATIAL_THRESHOLD_KM + 1),
        ("spatial_threshold_km", "2"),
        ("spatial_threshold_km", True),
        ("temporal_threshold_hours", 0),
        ("temporal_threshold_hours", -24),
        ("temporal_threshold_hours", float("nan")),
        ("temporal_threshold_hours", MAX_TEMPORAL_THRESHOLD_HOURS * 2),
        ("temporal_threshold_hours", None),
    ],
)
def test_pathological_thresholds_are_rejected_at_construction(field, value):
    # A wrong type is a TypeError, a wrong value a ValueError; both name the field.
    with pytest.raises((TypeError, ValueError), match=field):
        ClusteringParameters(**{field: value})


def test_the_guardrail_maxima_themselves_are_allowed():
    ClusteringParameters(MAX_SPATIAL_THRESHOLD_KM, MAX_TEMPORAL_THRESHOLD_HOURS)


def test_env_overrides_are_explicit_and_malformed_values_do_not_fall_back():
    assert ClusteringParameters.from_env({}) == ClusteringParameters()
    overridden = ClusteringParameters.from_env({"FIRMS_CLUSTER_SPATIAL_KM": "3.5"})
    assert overridden.spatial_threshold_km == 3.5
    assert overridden.temporal_threshold_hours == DEFAULT_TEMPORAL_THRESHOLD_HOURS
    assert overridden.source == "env"
    assert not overridden.is_default
    with pytest.raises(ValueError, match="FIRMS_CLUSTER_TEMPORAL_HOURS"):
        ClusteringParameters.from_env({"FIRMS_CLUSTER_TEMPORAL_HOURS": "three days"})
    with pytest.raises(ValueError, match="spatial_threshold_km"):
        ClusteringParameters.from_env({"FIRMS_CLUSTER_SPATIAL_KM": "-2"})


def test_resolve_parameters_accepts_one_form_at_a_time():
    assert resolve_parameters() == ClusteringParameters()
    partial = resolve_parameters(temporal_threshold_hours=24)
    assert partial.spatial_threshold_km == DEFAULT_SPATIAL_THRESHOLD_KM
    assert partial.temporal_threshold_hours == 24
    assert partial.source == "explicit"
    given = ClusteringParameters(1.0, 24.0)
    assert resolve_parameters(parameters=given) is given
    with pytest.raises(ValueError, match="not both"):
        resolve_parameters(1.0, parameters=given)


def test_cluster_events_validates_the_legacy_keyword_form_too():
    with pytest.raises(ValueError, match="spatial_threshold_km"):
        cluster_events(_controlled_set(), spatial_threshold_km=0)


# --- thresholds on the controlled set -------------------------------------


def test_defaults_keep_the_three_episodes_apart():
    events, _ = cluster_events(_controlled_set())
    assert sorted(e.observation_count for e in events) == [2, 3, 5]


def test_a_wider_radius_over_merges_the_two_same_day_groups():
    events, _ = cluster_events(_controlled_set(), parameters=ClusteringParameters(4.0, 72.0))
    assert sorted(e.observation_count for e in events) == [2, 8]


def test_a_longer_window_over_merges_the_reburn_into_the_first_group():
    events, _ = cluster_events(_controlled_set(), parameters=ClusteringParameters(2.0, 300.0))
    assert sorted(e.observation_count for e in events) == [3, 7]


def test_both_widened_collapse_everything_into_one_event():
    events, _ = cluster_events(_controlled_set(), parameters=ClusteringParameters(4.0, 300.0))
    assert [e.observation_count for e in events] == [10]


def test_a_tiny_radius_under_clusters_into_singletons():
    # Every neighbouring point in the set is at least ~110 m from the next.
    run = cluster_run(_controlled_set(), ClusteringParameters(0.1, 72.0))
    assert len(run.events) == 10
    assert all(e.link_count == 0 for e in run.events)
    assert run.links.accepted_pairs == 0


# --- diagnostics ---------------------------------------------------------


def test_diagnostics_explain_the_default_result():
    run = cluster_run(_controlled_set())
    d = diagnose(run, raw_observation_count=12)
    assert d.parameters == ClusteringParameters().to_dict()
    assert d.raw_observation_count == 12
    assert d.qualified_observation_count == 10
    assert d.event_count == 3
    assert d.compression_ratio == pytest.approx(10 / 3)
    assert d.singleton_count == 0
    assert d.multi_observation_event_count == 3
    assert d.observations_per_event["min"] == 2
    assert d.observations_per_event["max"] == 5
    assert d.observations_per_event["median"] == 3
    assert d.large_event_count == 0
    assert d.large_event_observations == 0
    assert d.large_event_observation_share == 0
    # Group A's five points are all within 2 km of each other (10 pairs) and
    # of the reburn's two (10 more), but the reburn is ten days away: those
    # ten pairs are exactly what the temporal rule kept apart. Group B: 3.
    assert d.links["spatial_pairs"] == 10 + 3 + 1 + 10
    assert d.links["accepted_pairs"] == 10 + 3 + 1
    assert d.links["rejected_by_time_pairs"] == 10
    assert d.links["max_accepted_gap_hours"] < 1
    assert d.links["max_accepted_distance_km"] < 0.5
    largest = d.largest_events[0]
    assert largest.observation_count == 5
    assert largest.link_count == 10
    assert largest.max_link_gap_hours < 1
    assert len(largest.lobes) == 1


def test_diagnostics_show_a_chain_merge_by_its_widest_link():
    """A wide radius merges A and B through links near the 3 km limit. The
    merged event's widest link is the tell, and lobes at 1 km still read it
    as two groups without re-clustering anything."""
    run = cluster_run(_controlled_set(), ClusteringParameters(4.0, 72.0))
    d = diagnose(run)
    merged = d.largest_events[0]
    assert merged.observation_count == 8
    # The widest accepted link is wider than the default radius: that single
    # number is what says the merge would not have happened at 2 km.
    assert DEFAULT_SPATIAL_THRESHOLD_KM < merged.max_link_distance_km <= 4.0
    assert [lobe.observation_count for lobe in merged.lobes] == [5, 3]
    assert merged.lobes[0].max_frp == 9.0
    assert merged.lobes[1].max_frp == 20.0
    assert sum(lobe.observation_count for lobe in merged.lobes) == merged.observation_count


def test_lobes_partition_the_event_and_never_change_membership():
    run = cluster_run(_controlled_set(), ClusteringParameters(4.0, 300.0))
    (only,) = run.events
    lobes = event_lobes(only, run.annotated, 1.0)
    assert sorted(chain.from_iterable(lobe.observation_indices for lobe in lobes)) == sorted(
        only.observation_indices
    )
    # At or above the clustering radius a spatial-only split can never find
    # more than one lobe: every clustered pair was already within it.
    assert len(event_lobes(only, run.annotated, 4.0)) == 1
    with pytest.raises(ValueError, match="lobe_distance_km"):
        event_lobes(only, run.annotated, 0)


def test_no_minimum_event_count_is_assumed():
    empty = pd.DataFrame(columns=["latitude", "longitude", "acq_date", "acq_time", "frp"])
    d = diagnose(cluster_run(empty))
    assert d.event_count == 0
    assert d.compression_ratio is None
    assert d.large_event_observation_share is None
    assert d.observations_per_event["median"] is None
    assert d.largest_events == []
    json.dumps(d.to_dict())
    format_summary(d)


def test_diagnostics_are_deterministic_and_json_serialisable():
    first = diagnose(cluster_run(_controlled_set())).to_dict()
    second = diagnose(cluster_run(_controlled_set().iloc[::-1].reset_index(drop=True))).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_threshold_sweep_reports_one_real_run_per_cell():
    rows = threshold_sweep(_controlled_set(), (2.0, 4.0), (72.0, 300.0))
    by_cell = {(r["spatial_threshold_km"], r["temporal_threshold_hours"]): r["event_count"] for r in rows}
    assert by_cell == {(2.0, 72.0): 3, (4.0, 72.0): 2, (2.0, 300.0): 2, (4.0, 300.0): 1}
    assert all(r["singleton_count"] == 0 for r in rows)


def test_window_selects_inclusive_acq_dates():
    selected = window(_controlled_set(), "2019-09-01", "2019-09-01")
    assert len(selected) == 8
    assert len(window(_controlled_set(), None, "2019-09-10")) == 8
    assert len(window(_controlled_set(), "2019-09-11", None)) == 2


def test_summary_text_has_no_em_dash():
    run = cluster_run(_controlled_set())
    d = diagnose(run)
    text = format_summary(d)
    assert "—" not in text
    assert "FireEvents" in text
    assert summarize_large_event(run.events[0], run.annotated).lobe_distance_km == 1.0
