"""Global Forest Watch Data API -- PLACEHOLDER, needs a free GFW account/API key.

Being registered for separately. Once GFW_API_KEY is set in .env, wire it
up here against:
  https://data-api.globalforestwatch.org/

Planned use (per DesignSpecs/environmental_assurance_spec_v2.md Section 9.1):
concession attribute lookup by point (spatialRel=esriSpatialRelIntersects) --
attribute-only, never store polygon geometry (Indonesian shapefile
publication restriction, see spec Section 2).
"""
from __future__ import annotations

from data_pipeline.config import GFW_API_KEY


def fetch_historical_sample() -> None:
    print("== Global Forest Watch Data API (placeholder) ==")
    if not GFW_API_KEY:
        print("GFW_API_KEY not set -- account still being provisioned. "
              "Skipping. See module docstring for the planned integration.\n")
        return
    raise NotImplementedError("Fill in once the GFW account/API key is ready.")


if __name__ == "__main__":
    fetch_historical_sample()
