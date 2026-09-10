// Guard rails for every map the console draws, not a frame. MapLibre clamps
// the camera to fit `maxBounds` and silently overrides any tighter view it is
// asked for (decision log, 2026-09-10), so these stay much wider than any
// viewport: roughly the Indian Ocean to Papua, southern Java to the
// Philippines. Inside them a user can drag and zoom freely. They exist so the
// scoped map can never wander to another continent, not to fence a scope.
export const REGIONAL_MAP_BOUNDS: [number, number, number, number] = [90, -12, 145, 25]
