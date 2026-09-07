import { useEvents } from '../../api/hooks'
import { useAppStore } from '../../store/useAppStore'
import { EventTable } from './EventTable'

export function TableSidebar() {
  const viewMode = useAppStore((s) => s.viewMode)
  const events = useEvents()

  return (
    <aside
      className={`h-full shrink-0 overflow-hidden border-l border-border-strong bg-panel shadow-2xl transition-[width] duration-200 ${
        viewMode === 'table' ? 'w-[560px]' : 'w-0'
      }`}
    >
      <div className="h-full w-[560px]">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Event queue</h2>
          <p className="text-xs text-text-muted">{events.length} monitored events</p>
        </div>
        <div className="h-[calc(100%-57px)]">
          <EventTable events={events} />
        </div>
      </div>
    </aside>
  )
}
