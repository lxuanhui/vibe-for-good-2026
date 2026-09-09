// Named import: maplibre-gl 6 dropped the default export.
import { setWorkerUrl } from 'maplibre-gl'
// ?worker&url, not ?url. The shipped maplibre-gl-worker.mjs is an ES module
// that imports maplibre-gl-shared.mjs, so copying the file verbatim gives a
// worker whose own imports 404. ?worker&url runs it through Rollup first.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

// maplibre-gl 6 finds its worker by resolving a *variable* filename against
// the bundled chunk's import.meta.url. Vite only rewrites a literal
// `new URL('./name', import.meta.url)`, so it never emits the worker and the
// browser requests /assets/maplibre-gl-worker.mjs, which does not exist.
//
// That request does not fail loudly. The SPA rewrite answers a missing asset
// with index.html, the module Worker never starts, and every tile and glyph
// request that would follow is simply never made -- the map paints its
// background layer and nothing else, with no console error. optimizeDeps in
// vite.config.ts handles the same bug for the dev server, which is why this
// only ever broke in production.
//
// setWorkerUrl wins over that runtime guess (the library reads
// `WORKER_URL || <guess>`), so pointing it at a chunk Vite has actually
// emitted is the whole fix. Imported for side effect from main.tsx, before
// anything renders a Map.
setWorkerUrl(workerUrl)
