import { APP_NAME } from '../../lib/brand'
import { EarthMark } from './EarthMark'

/** Mark plus wordmark, with an optional line under it for the screen's own
  label (the review period, "Create audit review"). One component so every
  header shows the name the same way and a rename touches lib/brand.ts only. */
export function Brand({ subtitle, className = '' }: { subtitle?: React.ReactNode; className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <EarthMark className="h-7 w-7 shrink-0 text-accent" />
      <div className="min-w-0">
        <div className="text-sm font-semibold tracking-wide">{APP_NAME}</div>
        {subtitle && <div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">{subtitle}</div>}
      </div>
    </div>
  )
}
