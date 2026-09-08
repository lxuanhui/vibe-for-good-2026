"""Documented estimate of manual evidence-reconstruction time.

This is a **reasoned estimate**, not a timed human-subject study -- there is
no analyst instrumented with a stopwatch behind these numbers, and nothing
here should be read as one. Each task below is estimated from what actually
operating the real public tool involves (navigating to it, entering the
event's coordinates/date range, waiting on the tool's own response time,
reading and transcribing the result) for one representative FireEvent case,
scoped exactly like `automated_run.py`'s case: an analyst who already has a
candidate hotspot cluster to investigate, not someone starting from "does
Indonesia have fires." Treat every number as order-of-magnitude, not a
precise measurement -- that imprecision is stated once here rather than
hedged on every call site.

Each `ManualTask.source` names the actual public tool an analyst would use
today, matching the provider this repo's own `sources/` modules automate:
FIRMS's Fire Archive Download Tool, Open-Meteo's historical archive plus
NASA POWER as the manual cross-check, the Global Peatland Map's own web
viewer, and the Copernicus Browser. `rationale` records the concrete steps
counted into the minute estimate, so a disagreement with the number is a
disagreement with a specific stated step, not a bare guess.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManualTask:
    task: str
    source: str
    estimated_minutes: float
    rationale: str


MANUAL_TASKS: list[ManualTask] = [
    ManualTask(
        task="Retrieve FIRMS history manually",
        source="FIRMS Fire Archive Download Tool (firms.modaps.eosdis.nasa.gov/download)",
        estimated_minutes=10.0,
        rationale=(
            "Navigate to the archive tool, draw/enter the region of interest, pick a sensor "
            "(VIIRS vs MODIS) and date range within the tool's day_range limits, submit the "
            "request, wait for the CSV to generate, download it, open it and confirm the "
            "columns match what's expected."
        ),
    ),
    ManualTask(
        task="Reconstruct event chronology",
        source="Spreadsheet, manual sort/group of the downloaded CSV",
        estimated_minutes=30.0,
        rationale=(
            "For a fire complex on the scale this repo's clustering demo finds (largest event: "
            "1,135 observations over 107 hours, 20.6km extent -- see README), sort by date/time, "
            "eyeball latitude/longitude proximity to decide which rows belong to the same fire "
            "versus a separate nearby one, and manually flag the boundary. Error-prone and "
            "genuinely slow at this observation count; the estimate assumes a practiced analyst, "
            "not a first attempt."
        ),
    ),
    ManualTask(
        task="Retrieve historical weather",
        source="Open-Meteo Historical Weather Archive (open-meteo.com) + NASA POWER as cross-check",
        estimated_minutes=35.0,
        rationale=(
            "The public Open-Meteo UI answers one date range per query, not seven relative "
            "windows at once, so this repo's own T-90d/T-30d/T-7d/T-72h/T-24h/event_duration/"
            "T0_to_T+48h windows (see enrichment/weather_enrichment.py) mean seven separate "
            "queries at roughly 3 minutes each (enter coordinates, enter dates, read off "
            "rainfall/temperature/humidity/wind) plus a manual 5-year rainfall baseline lookup "
            "and a NASA POWER cross-check query to sanity-check the rainfall figure."
        ),
    ),
    ManualTask(
        task="Inspect peat context",
        source="Global Peatland Map 2.0 web viewer (Greifswald Mire Centre)",
        estimated_minutes=15.0,
        rationale=(
            "Load the interactive viewer, pan/zoom to the event's footprint, visually judge "
            "whether the footprint and a buffer around it fall on mapped peat, and estimate "
            "distance to the nearest peat polygon if it doesn't -- all read by eye off a "
            "raster legend, not measured."
        ),
    ),
    ManualTask(
        task="Identify neighbouring events",
        source="FIRMS Fire Map (firms.modaps.eosdis.nasa.gov/map), same archive download",
        estimated_minutes=15.0,
        rationale=(
            "Pan the map around the event's centroid and time window looking for other hotspot "
            "clusters close enough in space and time to be worth noting as context, without any "
            "tool that lists them directly."
        ),
    ),
    ManualTask(
        task="Find suitable imagery metadata",
        source="Copernicus Browser (browser.dataspace.copernicus.eu)",
        estimated_minutes=15.0,
        rationale=(
            "Search Sentinel-1 GRD and Sentinel-2 L2A scenes over the event's bounding box and "
            "date window, note candidate scene IDs, acquisition dates, and cloud cover for "
            "Sentinel-2, since a hazy or cloud-covered scene close to the event date is often "
            "unusable."
        ),
    ),
    ManualTask(
        task="Assemble an evidence summary",
        source="Manual write-up (document/spreadsheet)",
        estimated_minutes=20.0,
        rationale=(
            "Compile the FIRMS chronology, weather windows, peat context, neighbouring events, "
            "and imagery candidates gathered above into one written summary a human reviewer can "
            "actually read, rather than seven disconnected browser tabs."
        ),
    ),
]


@dataclass(frozen=True)
class ManualBenchmarkResult:
    tasks: list[ManualTask]
    total_minutes: float

    def to_dict(self) -> dict:
        return {
            "total_minutes": round(self.total_minutes, 1),
            "tasks": [
                {
                    "task": t.task,
                    "source": t.source,
                    "estimated_minutes": t.estimated_minutes,
                    "rationale": t.rationale,
                }
                for t in self.tasks
            ],
        }


def manual_benchmark_total(tasks: list[ManualTask] = MANUAL_TASKS) -> ManualBenchmarkResult:
    return ManualBenchmarkResult(tasks=tasks, total_minutes=sum(t.estimated_minutes for t in tasks))


def _demo() -> None:
    result = manual_benchmark_total()
    print("== Manual evidence-reconstruction estimate (documented, not timed) ==")
    for t in result.tasks:
        print(f"  {t.estimated_minutes:5.1f} min  {t.task}  ({t.source})")
    print(f"Total: {result.total_minutes:.1f} minutes (~{result.total_minutes / 60:.2f} hours)\n")


if __name__ == "__main__":
    _demo()
