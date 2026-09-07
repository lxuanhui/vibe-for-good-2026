interface ChipProps {
  label: string
  tone?: 'default' | 'counter'
  active?: boolean
  title?: string
  onClick?: () => void
}

export function Chip({ label, tone = 'default', active, title, onClick }: ChipProps) {
  const toneClasses =
    tone === 'counter'
      ? 'border-status-urgent/40 text-status-urgent hover:bg-status-urgent/10'
      : 'border-status-good/40 text-status-good hover:bg-status-good/10'

  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`rounded border px-1.5 py-0.5 font-mono text-[11px] leading-none transition-colors ${toneClasses} ${
        active ? 'ring-1 ring-accent' : ''
      } ${onClick ? 'cursor-pointer' : 'cursor-default'}`}
    >
      {label}
    </button>
  )
}
