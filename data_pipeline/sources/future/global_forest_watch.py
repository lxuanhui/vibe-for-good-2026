"""Global Forest Watch Data API -- PLACEHOLDER, needs a free GFW account/API key.

Being registered for separately. Once GFW_API_KEY is set in .env, wire it
up here against:
  https://data-api.globalforestwatch.org/

Deprioritized post-MVP (DesignSpecs/Environmental_Assurance_Spec.md §30). If
built, planned use is concession attribute lookup by point
(spatialRel=esriSpatialRelIntersects) -- attribute-only; never store or
render the third-party concession polygon itself (§4: no public
named-concession directory).
"""
from __future__ import annotations

from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import GFW_API_KEY


def fetch_historical_sample() -> SourceResult:
    print("== Global Forest Watch Data API (placeholder) ==")
    provenance = Provenance(endpoint="https://data-api.globalforestwatch.org/", auth="api_key")
    if not GFW_API_KEY:
        print("GFW_API_KEY not set -- account still being provisioned. "
              "Skipping. See module docstring for the planned integration.\n")
        return SourceResult(
            source_name="Global Forest Watch Data API",
            status=SourceStatus.SKIPPED,
            provenance=provenance,
            summary="GFW_API_KEY not set",
        )
    raise NotImplementedError("Fill in once the GFW account/API key is ready.")


if __name__ == "__main__":
    fetch_historical_sample()
