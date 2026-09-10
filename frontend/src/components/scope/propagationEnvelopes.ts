import type { FeatureCollection, Polygon } from 'geojson'
import type { InvestigationMap } from '../../api/types'

// One polygon per candidate edge with a precomputed wind-oriented
// surface-spread envelope. Ownership is checked against the register
// selection, not the event whose drawer happens to be open: opening a
// contextual neighbour must not make its derived geometry look selected.
export function envelopePolygons(edges: readonly InvestigationMap['edges'][number][], selectedEventIds: readonly string[] = []): FeatureCollection<Polygon> {
  const selected = new Set(selectedEventIds)
  return {
    type: 'FeatureCollection',
    features: edges.flatMap((edge) => {
      // Ownership is deliberately required. Older or malformed responses
      // cannot safely associate an ellipse with the selected FireEvent, so
      // the conservative result is to draw no unrelated envelope.
      if (!edge.envelope || !selected.has(edge.envelope.ownerEventId)) return []
      return [{
        type: 'Feature' as const,
        geometry: { type: 'Polygon' as const, coordinates: [edge.envelope.polygon] },
        properties: { state: edge.state, sourceEventId: edge.sourceEventId, targetEventId: edge.targetEventId },
      }]
    }),
  }
}
