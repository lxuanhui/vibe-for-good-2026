import { scoreColor, scoreLabel } from '../../lib/color'

interface ScoreBadgeProps {
  score: number
  showLabel?: boolean
}

export function ScoreBadge({ score, showLabel = true }: ScoreBadgeProps) {
  const color = scoreColor(score)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {score}
      {showLabel && <span className="text-text-muted">{scoreLabel(score)}</span>}
    </span>
  )
}
