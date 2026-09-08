"""The three golden historical cases (issue #8) and the shared paths/helpers
that both `build_golden_cases.py` (regenerates fixtures from live sources)
and `tests/test_golden_regression.py` (asserts against them, no network) use.

Kept separate from the builder and the test so neither has to import the
other -- the test must never accidentally trigger a live fetch, and the
builder must never depend on pytest.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent

# Real 2019 haze-window FIRMS detections, hand-picked from the cached
# Sumatra/Kalimantan sample (`data_pipeline/output/firms_2019_haze_sample.csv`,
# `python -m data_pipeline.clustering.firms_clustering`) to cover the three
# shapes the acceptance criteria asks for. All three already sit on mapped
# peat when checked against the real Global Peatland Map 2.0 raster (this
# bbox is peat-dominated lowland), so "peat-related" here means the case
# chosen to *exercise* the peat-fraction metric meaningfully (a partial
# footprint fraction, not a trivial 100%/0%), not the only peat case.


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    event_id: str
    description: str


CASES: list[GoldenCase] = [
    GoldenCase(
        case_id="simple",
        event_id="FE-20190904-4904392c16",
        description=(
            "3 detections, 23.68h, 0.16km spatial extent -- a small, "
            "unambiguous single-location fire near South Sumatra (OKI "
            "peatland), the simplest shape a FireEvent can have without "
            "degenerating to a single point."
        ),
    ),
    GoldenCase(
        case_id="complex_multilobe",
        event_id="FE-20190901-ce19162367",
        description=(
            "1,135 detections, 107.43h, 20.55km spatial extent -- the "
            "largest event in the sample, spanning multiple detection "
            "lobes over 5 days. Same case already used as the worked "
            "example in `enrichment/weather_enrichment.py`, "
            "`enrichment/peat_context.py`, and `benchmark/`."
        ),
    ),
    GoldenCase(
        case_id="peat_related",
        event_id="FE-20190901-15f6721402",
        description=(
            "20 detections, 72.73h, 6.54km spatial extent, East Kalimantan. "
            "Footprint peat fraction is 71.43% (partial, sampled across a "
            "peat/mineral-soil boundary) rather than the complex case's "
            "uniform 100% -- exercises the peat-fraction metric's actual "
            "range, not just its saturated case."
        ),
    ),
]


def case_dir(case_id: str) -> Path:
    return GOLDEN_DIR / case_id


def observations_path(case_id: str) -> Path:
    return case_dir(case_id) / "observations.csv"


def expected_dir(case_id: str) -> Path:
    return case_dir(case_id) / "expected"


def weather_dir(case_id: str) -> Path:
    return case_dir(case_id) / "weather"


def peat_dir(case_id: str) -> Path:
    return case_dir(case_id) / "peat"


def imagery_dir(case_id: str) -> Path:
    return case_dir(case_id) / "imagery"


def strip_volatile(evidence_objects: list[dict]) -> list[dict]:
    """Drop `retrieved_at` (`datetime.now()` at generation time) before
    comparing or freezing evidence objects -- everything else `to_evidence_objects`
    produces is a pure function of the frozen inputs, so this is the only
    field that would otherwise make every regenerated fixture a diff."""
    return [{k: v for k, v in obj.items() if k != "retrieved_at"} for obj in evidence_objects]
