import type { EventStatus } from '../../api/types'
import { statusColor, statusLabel } from '../../lib/color'

export function StatusBadge({ status }: { status: EventStatus }) {
  const color = statusColor(status)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {statusLabel(status)}
    </span>
  )
}
