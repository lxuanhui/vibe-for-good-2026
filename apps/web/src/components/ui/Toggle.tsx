import type { ReactNode } from 'react'

interface ToggleProps {
  checked: boolean
  onChange: () => void
  label: string
  disabled?: boolean
  disabledHint?: string
  swatch?: ReactNode
  caption?: string
}

export function Toggle({ checked, onChange, label, disabled, disabledHint, swatch, caption }: ToggleProps) {
  return (
    <label
      className={`flex items-center justify-between gap-3 py-1 text-xs ${
        disabled ? 'cursor-not-allowed text-text-faint' : 'cursor-pointer text-text-muted hover:text-text'
      }`}
      title={disabled ? disabledHint : undefined}
    >
      <span className="flex min-w-0 items-start gap-2 pt-0.5">
        <span className="mt-0.5 flex shrink-0 items-center">{swatch}</span>
        <span className="min-w-0">
          <span className="block">{label}</span>
          {caption && <span className="mt-0.5 block text-[10px] text-text-faint">{caption}</span>}
        </span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={onChange}
        className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
          checked && !disabled ? 'bg-accent' : 'bg-border-strong'
        } ${disabled ? 'opacity-40' : ''}`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-bg transition-transform ${
            checked ? 'translate-x-3.5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </label>
  )
}
