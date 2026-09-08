"""BMKG (Badan Meteorologi, Klimatologi, dan Geofisika) -- PLACEHOLDER.

Indonesia's national weather/climate/geophysics agency. Being registered
for separately. BMKG publishes some open feeds (e.g. earthquake data,
public forecast XML/JSON) at data.bmkg.go.id without a key, but the
specifics this project needs (station-level historical weather, or a
fire-danger product) require confirming what an authenticated account
unlocks vs. what's already public -- do that check when the account
exists, then fill in below.
"""
from __future__ import annotations

from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import BMKG_API_KEY


def fetch_historical_sample() -> SourceResult:
    print("== BMKG (placeholder) ==")
    provenance = Provenance(endpoint="https://data.bmkg.go.id/", auth="api_key")
    if not BMKG_API_KEY:
        print("BMKG_API_KEY not set -- account still being provisioned. "
              "Skipping. See module docstring for notes.\n")
        return SourceResult(
            source_name="BMKG",
            status=SourceStatus.SKIPPED,
            provenance=provenance,
            summary="BMKG_API_KEY not set",
        )
    raise NotImplementedError("Fill in once BMKG credentials are ready.")


if __name__ == "__main__":
    fetch_historical_sample()
