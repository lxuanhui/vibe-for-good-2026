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
          <StatusBadge status={event.status} />
        </div>
        <div className="mb-2 text-xs text-text-muted">
          {event.location} · {formatCoord(event.lat, event.lon)}
        </div>
        <div className="mb-3 text-[11px] text-text-faint">First detected {formatDate(event.firstDetected)}</div>
        <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <dt className="text-text-muted">Temperature</dt>
          <dd>{c.temperatureC.toFixed(1)}°C</dd>
          <dt className="text-text-muted">Humidity</dt>
          <dd>{c.relativeHumidity}%</dd>
          <dt className="text-text-muted">Wind</dt>
          <dd>
            {c.windSpeedKmh} km/h @ {c.windDirectionDeg}°
          </dd>
          <dt className="text-text-muted">Recent rainfall</dt>
          <dd>{c.recentRainfallMm} mm</dd>
        </dl>
        <Button
          variant="primary"
          className="w-full"
          disabled={!event.qualifiesForInvestigation}
          onClick={() => openReport(event.id)}
        >
          {event.qualifiesForInvestigation ? 'Open investigation report' : 'Not qualified for investigation'}
        </Button>
      </div>
    </Popup>
  )
}
