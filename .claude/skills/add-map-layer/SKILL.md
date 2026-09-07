---
name: add-map-layer
description: Add or change an overlay layer on the console map (FIRMS, SAR, KHG peat units, concessions, fire-complex links, raster tiles). Use when a new data layer needs to render, when a layer needs a toggle or a legend swatch, or when wiring timeline date-availability for a sensor. Covers the mandated source+layer pattern and the five files a layer touches.
---

# Adding a map overlay layer

The UI spec (`DesignSpecs/assurance_console_ui_spec.md` §2.2) is explicit:
adding an overlay means **"add a source + layer pointing at an endpoint"**,
never a bespoke renderer per data type. If a change needs custom drawing code
per data source, it is going the wrong way.

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
   in a component; the UI spec requires one consistent scheme across map
   markers, table status, and report scores.
5. **`frontend/src/components/map/MapView.tsx`** — a `useOverlay(...)` call
   and a `<Source>` / `<Layer>` pair, guarded on the data being non-null.
   Then **`LayerControlPanel.tsx`** — an entry in `GEOJSON_LAYERS` or
   `RASTER_LAYERS` with a swatch matching the map paint, and a caption if the
   layer needs a caveat.

## Sensor cadence is a feature, not a bug

If the layer comes from a sensor with a real revisit cadence, add its
available dates to `frontend/src/api/fixtures/dates.ts` and, if it should show
in the scrubber's availability badges, to `DATE_GATED_LAYERS` in
`TimelineScrubber.tsx`. The spec (§2.3) requires the UI to show "no pass at
this date" rather than silently rendering stale or empty data. Sparse SAR
coverage is the honest picture, not a gap to paper over.

## Known seams to respect

- `client.ts` is the swap point for a real backend — every fetch mirrors the
  endpoint contract in UI spec §5. New layers fetch through `useOverlay`, not
  through a direct `fetch` in a component. (`isLayerAvailable` is currently
  imported straight from fixtures in `TimelineScrubber` — a hole in that seam,
  don't widen it.)
- `fetchEvents`/`fetchOverlay` accept a bbox that nothing currently passes.
  If viewport-driven fetching gets wired up, it goes there, not into MapView.
- A layer sourced from real pipeline output must state so in its caption, with
  its date range, the way the FIRMS pipeline toggle does — the demo must never
  blur which data is real and which is a fixture.
- Never render or store raw concession/peatland boundary geometry (spec v2
  §2). Attribute lookups only.
