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
      // The artifact may retain envelope dimensions for an edge whose target
      // is outside the projected reach. The graph state is the backend's
      // deterministic spatial-plus-temporal eligibility decision; geometry
      // alone must not turn that failed compatibility check into a drawing.
      if (edge.state !== 'PROPAGATION_COMPATIBLE' || !edge.envelope || !selected.has(edge.envelope.ownerEventId)) return []
      return [{
        type: 'Feature' as const,
        geometry: { type: 'Polygon' as const, coordinates: [edge.envelope.polygon] },
        properties: { state: edge.state, sourceEventId: edge.sourceEventId, targetEventId: edge.targetEventId },
      }]
    }),
  }
}
