"""Global Peatland Database (Greifswald Mire Centre) -- Global Peatland Map 2.0.

No REST API. Distributed as a single zip archive (confirmed 3.6MB,
application/zip) via a Nextcloud share, or as a Google Earth Engine asset
(needs a GEE account/auth, out of scope for this spike). This confirms the
direct-download file is reachable and reports its size -- there is no
per-coordinate query to test (it's one static dataset you'd unzip and
clip locally after downloading) and no historical dimension
(single-snapshot product).

Source: https://greifswaldmoor.de/global-peatland-database-en.html
GEE asset (future option): projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE
"""
from __future__ import annotations

from data_pipeline.common.http import SESSION

DOWNLOAD_URL = "https://nextcloud.uni-greifswald.de/index.php/s/s7Ln5QKxdQG5aaA/download"


def fetch_historical_sample() -> None:
    print("== Global Peatland Database ==")
    try:
        resp = SESSION.get(DOWNLOAD_URL, stream=True, timeout=15)
        status = resp.status_code
        size = resp.headers.get("Content-Length")
        content_type = resp.headers.get("Content-Type")
        resp.close()
    except Exception as exc:  # noqa: BLE001 -- diagnostic script, report and move on
        print(f"Direct-download link unreachable: {exc}\n")
        return

    print(f"Direct-download link reachable: HTTP {status}, Content-Type={content_type}, "
          f"Content-Length={size or 'unknown'}")
    print("Single static global raster, no time series, no REST query API -- "
          "ingestion would be a one-off download + local point-in-polygon/raster "
          "lookup, not a cron-polled endpoint. GEE offers the same dataset as an "
          "asset if that access path is preferred later.\n")


if __name__ == "__main__":
    fetch_historical_sample()
