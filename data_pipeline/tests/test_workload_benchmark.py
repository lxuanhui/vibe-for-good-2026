from data_pipeline.benchmark import automated_run
from data_pipeline.benchmark.automated_run import (
    AUDIT_ID,
    DEST_EVENTS,
    PEAT_EVIDENCE_FIELDS_POSSIBLE,
    NeighbouringEvent,
    count_events_in_scope,
    evidence_field_completeness,
    find_neighbouring_events,
)
from data_pipeline.benchmark.manual_estimate import MANUAL_TASKS, manual_benchmark_total
from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrichment.weather_enrichment import (
    EVIDENCE_METRICS_PER_WINDOW,
    WINDOW_NAMES,
)


def _event(
    event_id: str,
    centroid: tuple[float, float],
    first_detection: str,
    last_detection: str | None = None,
) -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection=first_detection,
        last_detection=last_detection or first_detection,
        duration_hours=0.0,
        observation_count=1,
        centroid=centroid,
        bbox=(centroid[1], centroid[0], centroid[1], centroid[0]),
        spatial_extent_km=0.0,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


# --- manual_estimate.py ----------------------------------------------------


def test_manual_tasks_cover_every_checklist_item_in_the_issue():
    task_names = {t.task for t in MANUAL_TASKS}
    assert task_names == {
        "Retrieve FIRMS history manually",
        "Reconstruct event chronology",
        "Retrieve historical weather",
        "Inspect peat context",
        "Identify neighbouring events",
        "Find suitable imagery metadata",
        "Assemble an evidence summary",
    }


def test_manual_benchmark_total_sums_task_minutes():
    result = manual_benchmark_total()
    assert result.total_minutes == sum(t.estimated_minutes for t in MANUAL_TASKS)
    assert result.total_minutes > 0


def test_manual_benchmark_to_dict_round_trips_task_count():
    result = manual_benchmark_total()
    d = result.to_dict()
    assert len(d["tasks"]) == len(MANUAL_TASKS)
    assert d["total_minutes"] == round(result.total_minutes, 1)


# --- find_neighbouring_events -----------------------------------------------


def test_finds_nearby_event_within_radius_and_window():
    target = _event("FE-TARGET", (-2.500, 114.000), "2019-09-01T00:00:00+00:00")
    near = _event("FE-NEAR", (-2.510, 114.010), "2019-09-05T00:00:00+00:00")  # ~1.6km, 4 days
    neighbours = find_neighbouring_events(target, [target, near])
    assert [n.event_id for n in neighbours] == ["FE-NEAR"]
    assert isinstance(neighbours[0], NeighbouringEvent)
    assert neighbours[0].distance_km < 5


def test_excludes_event_outside_spatial_radius():
    target = _event("FE-TARGET", (-2.500, 114.000), "2019-09-01T00:00:00+00:00")
    far = _event("FE-FAR", (1.050, 101.450), "2019-09-01T00:00:00+00:00")  # hundreds of km away
    neighbours = find_neighbouring_events(target, [target, far], radius_km=50.0)
    assert neighbours == []


def test_excludes_event_outside_temporal_window():
    target = _event("FE-TARGET", (-2.500, 114.000), "2019-09-01T00:00:00+00:00")
    old = _event("FE-OLD", (-2.501, 114.001), "2018-01-01T00:00:00+00:00")  # same spot, over a year earlier
    neighbours = find_neighbouring_events(target, [target, old], window_days=30.0)
    assert neighbours == []


def test_excludes_self_from_its_own_neighbour_list():
    target = _event("FE-TARGET", (-2.500, 114.000), "2019-09-01T00:00:00+00:00")
    neighbours = find_neighbouring_events(target, [target])
    assert neighbours == []


# --- evidence_field_completeness --------------------------------------------


def test_completeness_is_full_when_every_field_present():
    max_weather = len(WINDOW_NAMES) * EVIDENCE_METRICS_PER_WINDOW
    weather_objects = [{"evidence_id": f"w{i}"} for i in range(max_weather)]
    peat_objects = [{"evidence_id": f"p{i}"} for i in range(PEAT_EVIDENCE_FIELDS_POSSIBLE)]
    result = evidence_field_completeness(weather_objects, peat_objects)
    assert result["completeness_fraction"] == 1.0


def test_completeness_reflects_partial_data():
    max_weather = len(WINDOW_NAMES) * EVIDENCE_METRICS_PER_WINDOW
    weather_objects = [{"evidence_id": f"w{i}"} for i in range(max_weather // 2)]
    peat_objects = []
    result = evidence_field_completeness(weather_objects, peat_objects)
    assert 0 < result["completeness_fraction"] < 1.0
    assert result["weather_fields_present"] == max_weather // 2
    assert result["peat_fields_present"] == 0


# --- scope compression ------------------------------------------------------


def test_scope_count_is_not_measurable_without_a_boundary():
    event = _event("FE-TARGET", (-2.5, 114.0), "2019-09-01T00:00:00+00:00")
    assert count_events_in_scope([event]) is None


def test_scope_count_includes_event_bbox_intersection_and_buffer():
    event = _event("FE-TARGET", (-2.5, 114.0), "2019-09-01T00:00:00+00:00")
    outside = _event("FE-OUTSIDE", (-2.8, 114.4), "2019-09-01T00:00:00+00:00")
    boundary = (113.99, -2.51, 114.01, -2.49)
    assert count_events_in_scope([event, outside], boundary) == 1
    assert count_events_in_scope([event, outside], boundary, buffer_km=50) == 2


# --- committed benchmark inputs --------------------------------------------


def test_committed_artifacts_reconcile_with_source_export():
    artifact = automated_run._read_artifact(DEST_EVENTS)
    scope = artifact["audits"][AUDIT_ID]["scope"]

    assert (
        len(automated_run.load_observations())
        == artifact["source"]["observationsUsed"]
    )
    assert scope["eventCount"] == len(
        artifact["audits"][AUDIT_ID]["events"]
    )
