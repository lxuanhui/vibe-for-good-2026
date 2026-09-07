import { Marker } from 'react-map-gl/maplibre'
import type { FireEvent } from '../../api/types'
import { useAppStore } from '../../store/useAppStore'
import { isActiveOnDate } from '../../lib/events'
import { EventInfoCard } from './EventInfoCard'

export function EventMarkers({ events }: { events: FireEvent[] }) {
  const activeDate = useAppStore((s) => s.activeDate)
  const selectedEventId = useAppStore((s) => s.selectedEventId)
  const selectEvent = useAppStore((s) => s.selectEvent)
  const selectedEvent = events.find((e) => e.id === selectedEventId)

  return (
    <>
      {events.map((event) => {
        const active = isActiveOnDate(event, activeDate)
        const selected = selectedEventId === event.id
        return (
          <Marker
            key={event.id}
            longitude={event.lon}
            latitude={event.lat}
            onClick={(e) => {
              e.originalEvent.stopPropagation()
              selectEvent(event.id)
            }}
          >
            <div className="relative cursor-pointer">
              {active ? (
                <span className="relative flex h-3 w-3">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-urgent opacity-60" />
                  <span className="relative block h-3 w-3 rounded-full bg-status-urgent shadow-[0_0_10px_3px_rgba(239,68,68,0.55)]" />
                </span>
              ) : (
                <span className="block h-3 w-3 rounded-full border-2 border-status-quiet bg-bg/70" />
              )}
              {selected && <span className="pointer-events-none absolute -inset-2 rounded-full ring-2 ring-accent" />}
            </div>
          </Marker>
        )
      })}
      {selectedEvent && <EventInfoCard event={selectedEvent} onClose={() => selectEvent(null)} />}
    </>
  )
}
