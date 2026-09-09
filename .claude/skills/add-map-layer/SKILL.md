---
name: add-map-layer
description: Add or change an overlay layer on the console map (FIRMS, SAR, KHG peat units, concessions, fire-complex links, raster tiles). Use when a new data layer needs to render, when a layer needs a toggle or a legend swatch, or when wiring timeline date-availability for a sensor. Covers the mandated source+layer pattern and the five files a layer touches.
---

# Adding a map overlay layer

The canonical spec (`DesignSpecs/Environmental_Assurance_Spec.md` §13,
Spatial Investigation Workspace) lists the map's overlay layers. The
implementation convention this repo follows — **"add a source + layer
pointing at an endpoint," never a bespoke renderer per data type** — is an
engineering convention, not spec text, but it still governs how you add one.
If a change needs custom drawing code per data source, it is going the wrong
way.

## The five files, in order

1. **`frontend/src/api/types.ts`** — add the id to `OverlayLayerId` (GeoJSON
   points/polygons/lines) or `RasterLayerId` (imagery tiles). These unions
   drive everything else; TypeScript will now point at each remaining step.
2. **`frontend/src/api/fixtures/overlays.ts`** — add the feature builder and a
   case in `getOverlay`, plus its availability in `isLayerAvailable`. Until
   there is a real backend, this is where the layer's data lives.
3. **`frontend/src/store/useAppStore.ts`** — add the id to the
   `layerVisibility` initial record with a sensible default. Layers that are
   noisy or expensive default to `false`.
4. **`frontend/src/lib/layerColors.ts`** — add the colour. Do not inline a hex
   in a component; this repo keeps one consistent scheme across map markers,
   table status, and report scores.
5. **`frontend/src/components/scope/ScopedMapLanding.tsx`** — the console's
   current map surface (issue #75). A `useOverlay(...)` call and a `<Source>`
   / `<Layer>` pair, guarded on the data being non-null. Then
   **`LayerControlPanel.tsx`** — an entry in `GEOJSON_LAYERS` or
   `RASTER_LAYERS` with a swatch matching the map paint, and a caption if the
   layer needs a caveat. Pass `scoped` where the panel is mounted scoped; it
   filters `GEOJSON_LAYERS` down to `firms` only until the other layers have a
   scoped-map story.

## Sensor cadence is a feature, not a bug

If the layer comes from a sensor with a real revisit cadence, add its
available dates to `frontend/src/api/fixtures/dates.ts`. The canonical spec
(§13) requires the timeline to expose sensor availability and missing passes
rather than silently rendering stale or empty data — sparse SAR coverage is
the honest picture, not a gap to paper over. There is currently no live
surface for this: `TimelineScrubber.tsx` and `MapView.tsx` (its
`DATE_GATED_LAYERS` availability badges included) were deleted as dead code
once issue #75 stopped mounting `MapView`, and `ScopedMapLanding.tsx` has no
scrubber yet. Rebuild the availability-badge pattern there when a date-gated
layer actually needs it, rather than reviving the deleted file.

## Known seams to respect

- `client.ts` is the swap point for a real backend — every fetch mirrors the
  endpoint contract in `Environmental_Assurance_Spec.md` §24 (API). New layers
  fetch through `useOverlay`, not through a direct `fetch` in a component.
- `fetchEvents`/`fetchOverlay` accept a bbox that nothing currently passes.
  If viewport-driven fetching gets wired up, it goes into the map component
  that owns the source, not into a fixture or the store.
- A layer sourced from real pipeline output must state so in its caption, with
  its date range, the way the FIRMS pipeline toggle does — the demo must never
  blur which data is real and which is a fixture.
- An auditor-uploaded audit-scope boundary may now be stored privately
  (`Environmental_Assurance_Spec.md` §6.2–6.3) — that policy changed from the
  legacy specs' blanket "never store boundary geometry." What is still a hard
  non-goal (§4) is a *public* named-concession directory or rendering
  third-party concession polygons beyond an attribute-only lookup.
