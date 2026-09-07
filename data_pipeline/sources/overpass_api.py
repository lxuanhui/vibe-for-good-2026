"""Overpass API -- OpenStreetMap roads/settlements query.

Free, no auth, current-data by default. Historical ("attic") queries are
documented as possible on overpass-api.de via a [date:"..."] setting, but
empirically this instance does NOT honor it: a control query against
central Jakarta (which has had thousands of mapped roads since well
before 2020) returns 0 elements for every [date:...] value tried
(2010, 2015, 2020) while the dateless query returns 12000+. That's not
"no roads existed then" -- it's the instance's attic/history database
being empty or unsupported for this query form. Conclusion: treat
Overpass as current-snapshot-only for this project; don't build any
"roads as of fire date" logic on top of [date:...] without re-verifying
against a different instance first.

Docs: https://wiki.openstreetmap.org/wiki/Overpass_API
"""
from __future__ import annotations

from data_pipeline.common.http import SESSION
from data_pipeline.config import POINTS

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Central Jakarta -- used only as a control point known to have had dense
# OSM road coverage well before 2020, to sanity-check the attic query.
_JAKARTA_CONTROL_POINT = (-6.2, 106.8)


def query_roads_near(lat: float, lon: float, radius_m: int = 5000, as_of_date: str | None = None) -> dict:
    date_setting = f'[date:"{as_of_date}T00:00:00Z"]' if as_of_date else ""
    ql = f"""
    [out:json]{date_setting}[timeout:25];
    (
      way["highway"](around:{radius_m},{lat},{lon});
    );
    out center;
    """
    resp = SESSION.post(OVERPASS_URL, data={"data": ql})
    resp.raise_for_status()
    return resp.json()


def fetch_historical_sample() -> None:
    print("== Overpass API (OpenStreetMap) ==")
    name, (lat, lon) = next(iter(POINTS.items()))

    current = query_roads_near(lat, lon)
    print(f"Current roads within 5km of {name}: {len(current.get('elements', []))} ways")

    jlat, jlon = _JAKARTA_CONTROL_POINT
    try:
        jakarta_now = query_roads_near(jlat, jlon, radius_m=3000)
        now_count = len(jakarta_now.get("elements", []))
        attic_counts = {}
        for as_of in ("2010-01-01", "2015-01-01", "2020-01-01"):
            result = query_roads_near(jlat, jlon, radius_m=3000, as_of_date=as_of)
            attic_counts[as_of] = len(result.get("elements", []))
        print(f"Control point (central Jakarta): dateless query = {now_count} ways; "
              f"[date:...] queries = {attic_counts}")
        if now_count > 0 and all(c == 0 for c in attic_counts.values()):
            print("[date:...] returned 0 for every historical date against a point known "
                  "to have had dense road coverage well before 2020 -- this instance's attic/"
                  "history database is empty or unsupported for this query form, not actually "
                  "returning historical snapshots. Treat Overpass as current-snapshot-only; "
                  "don't build 'roads as of fire date' logic on [date:...] without re-verifying "
                  "against a different instance.\n")
        else:
            print("[date:...] returned non-zero, non-trivial results -- attic queries appear "
                  "to work on this instance; worth deeper verification before relying on it.\n")
    except Exception as exc:  # noqa: BLE001 -- diagnostic script, report and move on
        print(f"[date:...] attic query failed outright on this instance ({exc}) -- "
              "treat roads/settlements as static-current only via the public "
              "API; don't rely on historical OSM snapshots.\n")


if __name__ == "__main__":
    fetch_historical_sample()
