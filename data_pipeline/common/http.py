"""Shared HTTP session used by every source script.

Caching avoids hammering free/rate-limited public APIs while iterating on
this spike; retries paper over the transient 5xx/timeouts these services
occasionally return. Same pattern Open-Meteo's own docs recommend.

`truststore` makes Python's ssl module verify against the OS certificate
store instead of certifi's bundled one. Needed because some .gov servers
(NASA FIRMS observed here) don't send their full intermediate chain and
rely on the client fetching it via AIA -- Windows does this natively
(curl/Windows SChannel succeed) but OpenSSL/certifi verification does not,
so plain requests fails with CERTIFICATE_VERIFY_FAILED on those hosts
specifically while every other HTTPS call works fine.
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()

import requests_cache
from retry_requests import retry

from data_pipeline.config import ROOT

_cache_path = str(ROOT / ".cache")
_cached = requests_cache.CachedSession(_cache_path, expire_after=3600)
SESSION = retry(_cached, retries=5, backoff_factor=0.2)

# Overpass (and possibly other free/abuse-sensitive public APIs) reject the
# default "python-requests/x.y" User-Agent outright with 406 Not Acceptable.
SESSION.headers.update({"User-Agent": "vibe-for-good-2026-data-pipeline/0.1 (research spike)"})
