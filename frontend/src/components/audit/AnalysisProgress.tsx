import { useEffect, useState } from 'react'

function elapsedLabel(startedAt: string, now: number): string {
  const started = Date.parse(startedAt)
  const seconds = Math.max(0, Math.floor((now - (Number.isNaN(started) ? now : started)) / 1000))
  return `${seconds}s elapsed`
}

export function AnalysisProgress({ startedAt, stage, returnMessage }: { startedAt: string; stage?: string | null; returnMessage: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return <div role="status" aria-live="polite" className="mt-3 rounded border border-accent/40 bg-accent/10 p-3 text-[11px] text-text-muted">
    <div className="flex items-center gap-2 font-semibold text-text">
      <span aria-hidden="true" className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
      <span>Generating investigation analysis...</span>
      <span className="ml-auto font-mono text-[10px] text-accent">{elapsedLabel(startedAt, now)}</span>
    </div>
    <p className="mt-2">Usually takes about a minute. Two rounds run: Investigator and Skeptic each assess the evidence, then answer each other.</p>
    <p className="mt-1">{returnMessage}</p>
    <p className="mt-1 font-medium text-accent">{stage || 'Starting'}</p>
  </div>
}
