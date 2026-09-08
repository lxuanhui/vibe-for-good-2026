"""Combine the manual estimate and the automated run into the workload-
reduction comparison issue #7 asks for, and print/save it.

Run with `python -m data_pipeline.benchmark.report`.

## Scope -- read before citing a number from this module

This benchmarks one task: reconstructing the evidence for one FireEvent
(FIRMS chronology, weather windows, peat context, neighbouring events,
imagery metadata, assembled into a summary). It is not a measurement of the
whole audit workflow, which also includes scope definition, screening
judgement across many events, field verification, and report sign-off --
none of which is timed here. Do not extrapolate this percentage to "the
audit is N% faster." The manual side (`manual_estimate.py`) is a documented
estimate of what operating the real public tools requires, not a timed
human trial; the automated side (`automated_run.py`) is a real, timed run
of this repo's own pipeline code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from data_pipeline.benchmark.automated_run import (
    AutomatedBenchmarkResult,
    run_automated_benchmark,
)
from data_pipeline.benchmark.manual_estimate import (
    ManualBenchmarkResult,
    manual_benchmark_total,
)
from data_pipeline.config import OUTPUT_DIR

SCOPE_NOTE = (
    "Scope: environmental evidence-reconstruction for one FireEvent only. "
    "Do not read this percentage as the acceleration of the whole audit workflow."
)


@dataclass(frozen=True)
class WorkloadReductionReport:
    manual: ManualBenchmarkResult
    automated: AutomatedBenchmarkResult
    manual_seconds: float
    automated_seconds: float
    percent_reduction: float
    scope_note: str = SCOPE_NOTE

    def to_dict(self) -> dict:
        return {
            "scope_note": self.scope_note,
            "manual_reconstruction_time_seconds": round(self.manual_seconds, 1),
            "manual_reconstruction_time_minutes": round(self.manual_seconds / 60, 2),
            "automated_reconstruction_time_seconds": round(self.automated_seconds, 3),
            "percent_reduction_for_this_task": round(self.percent_reduction, 1),
            "observations_to_events_compression": self.automated.observations_to_events_compression,
            "events_to_human_review_queue_compression": self.automated.events_to_review_queue_compression,
            "events_to_human_review_queue_note": self.automated.events_to_review_queue_note,
            "evidence_field_completeness": self.automated.evidence_completeness,
            "manual_interactions_in_automated_run": self.automated.manual_interactions,
            "manual_benchmark": self.manual.to_dict(),
            "automated_benchmark": self.automated.to_dict(),
        }


def build_report(buffer_km: float = 5.0) -> WorkloadReductionReport:
    manual = manual_benchmark_total()
    automated = run_automated_benchmark(buffer_km=buffer_km)

    manual_seconds = manual.total_minutes * 60.0
    automated_seconds = automated.total_seconds
    percent_reduction = (
        round((1 - automated_seconds / manual_seconds) * 100, 1)
        if manual_seconds
        else 0.0
    )

    return WorkloadReductionReport(
        manual=manual,
        automated=automated,
        manual_seconds=manual_seconds,
        automated_seconds=automated_seconds,
        percent_reduction=percent_reduction,
    )


def _demo() -> None:
    print("== Auditor workload-reduction benchmark (issue #7) ==")
    print(SCOPE_NOTE)
    print()

    report = build_report()

    print(
        f"Manual estimate:    {report.manual.total_minutes:.1f} min ({report.manual_seconds:.0f}s)"
    )
    print(
        f"Automated run:      {report.automated_seconds:.2f}s for event {report.automated.event_id}"
    )
    print(f"Reduction for this task: {report.percent_reduction:.1f}%")
    print()
    print(
        f"Raw FIRMS observations -> FireEvents: {report.automated.observation_count} -> "
        f"{report.automated.event_count} ({report.automated.observations_to_events_compression}x)"
    )
    print(
        f"FireEvents -> human-review queue: {report.automated.event_count} -> "
        f"{report.automated.review_queue_count} "
        f"({report.automated.events_to_review_queue_compression}x) "
        f"-- {report.automated.events_to_review_queue_note}"
    )
    print(f"Evidence-field completeness: {report.automated.evidence_completeness}")
    print(
        f"Manual interactions in the automated run: {report.automated.manual_interactions}"
    )

    out_path = OUTPUT_DIR / "workload_reduction_report.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\nSaved full report to {out_path}\n")


if __name__ == "__main__":
    _demo()
