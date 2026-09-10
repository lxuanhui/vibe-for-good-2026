import type { FeatureCollection, Polygon } from 'geojson'
import type { InvestigationMap } from '../../api/types'

// One polygon per candidate edge with a precomputed wind-oriented
// surface-spread envelope. The owner is explicit because the map combines
// the focused-event graph with the wider register selection graph.
export function envelopePolygons(edges: readonly InvestigationMap['edges'][number][], ownerEventId?: string): FeatureCollection<Polygon> {
  return {
    type: 'FeatureCollection',
    features: edges.flatMap((edge) => {
      // Ownership is deliberately required. Older or malformed responses
      // cannot safely associate an ellipse with the selected FireEvent, so
      // the conservative result is to draw no unrelated envelope.
      if (!edge.envelope || !ownerEventId || edge.envelope.ownerEventId !== ownerEventId) return []
      return [{
        type: 'Feature' as const,
        geometry: { type: 'Polygon' as const, coordinates: [edge.envelope.polygon] },
        properties: { state: edge.state, sourceEventId: edge.sourceEventId, targetEventId: edge.targetEventId },
      }]
    }),
  }
}
