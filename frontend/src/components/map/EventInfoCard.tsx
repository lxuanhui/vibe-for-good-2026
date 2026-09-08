import { Popup } from 'react-map-gl/maplibre'
import type { FireEvent } from '../../api/types'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import { StatusBadge } from '../ui/StatusBadge'
import { formatCoord, formatDate } from '../../lib/format'

interface EventInfoCardProps {
  event: FireEvent
  onClose: () => void
}

export function EventInfoCard({ event, onClose }: EventInfoCardProps) {
  const openReport = useAppStore((s) => s.openReport)
  const c = event.currentConditions
  const generated = event.scopeRelation != null

  return (
    <Popup
      longitude={event.lon}
      latitude={event.lat}
      onClose={onClose}
      closeOnClick={false}
      closeButton={false}
      anchor="bottom"
      offset={16}
    >
      <div className="w-64 rounded-lg border border-border-strong bg-panel p-3 text-text shadow-xl">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold">{event.id}</span>
          {event.status ? <StatusBadge status={event.status} /> : <span className="text-[10px] text-status-moderate">{event.scopeRelation?.replaceAll('_', ' ')}</span>}
        </div>
        <div className="mb-2 text-xs text-text-muted">
          {event.location ?? `${event.scopeRelation ?? 'FireEvent'} · ${formatCoord(event.lat, event.lon)}`}
        </div>
        <div className="mb-3 text-[11px] text-text-faint">First detected {formatDate(event.firstDetected)} · Last {formatDate(event.lastDetected ?? event.firstDetected)}</div>
        {generated ? (
          <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-text-muted">Observations</dt><dd>{event.observationCount ?? 0}</dd>
            <dt className="text-text-muted">Priority</dt><dd>{event.investigationPriority ?? '—'}</dd>
            <dt className="text-text-muted">Evidence</dt><dd>{event.evidenceSufficiency ?? '—'}</dd>
            <dt className="text-text-muted">Peat overlap</dt><dd>{event.peatFraction != null ? `${(event.peatFraction * 100).toFixed(0)}%` : 'N/A'}</dd>
          </dl>
        ) : c ? (
          <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-text-muted">Temperature</dt><dd>{c.temperatureC.toFixed(1)}°C</dd>
            <dt className="text-text-muted">Humidity</dt><dd>{c.relativeHumidity}%</dd>
            <dt className="text-text-muted">Wind</dt><dd>{c.windSpeedKmh} km/h @ {c.windDirectionDeg}°</dd>
            <dt className="text-text-muted">Recent rainfall</dt><dd>{c.recentRainfallMm} mm</dd>
          </dl>
        ) : null}
        <Button
          variant="primary"
          className="w-full"
          disabled={generated || !event.qualifiesForInvestigation}
          onClick={() => openReport(event.id)}
        >
          {generated ? 'Analysis not yet available' : event.qualifiesForInvestigation ? 'Open investigation report' : 'Not qualified for investigation'}
        </Button>
      </div>
    </Popup>
  )
}
