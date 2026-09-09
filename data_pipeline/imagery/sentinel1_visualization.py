"""Deterministic display conversion for Sentinel-1 RTC/terrain-corrected GRD.

This module intentionally accepts already-authoritative backscatter arrays;
it does not invent pixels, upsample, or denoise away spatial features.  The
frontend receives only the resulting 8-bit preview plus provenance while the
raw Copernicus product reference remains attached to the EvidenceObject.
"""

from __future__ import annotations

import numpy as np

DISPLAY_PROCESSING = "linear VV/VH → dB; per-scene 2–98% percentile stretch; no generative enhancement"


def backscatter_to_display(linear_backscatter: np.ndarray) -> np.ndarray:
    """Convert finite, non-negative linear backscatter deterministically to uint8.

    The 2–98% stretch is deliberately per scene: it improves visual reading
    without changing raw values used for analysis. Invalid / non-positive
    cells render black rather than being reconstructed.
    """
    source = np.asarray(linear_backscatter, dtype=np.float32)
    valid = np.isfinite(source) & (source > 0)
    out = np.zeros(source.shape, dtype=np.uint8)
    if not np.any(valid):
        return out
    db = np.zeros_like(source)
    db[valid] = 10 * np.log10(source[valid])
    low, high = np.percentile(db[valid], (2, 98))
    if high <= low:
        out[valid] = 128
        return out
    out[valid] = np.clip((db[valid] - low) * 255 / (high - low), 0, 255).astype(np.uint8)
    return out
