import { useAppStore } from '../../store/useAppStore'

export function ViewModeToggle() {
  const viewMode = useAppStore((s) => s.viewMode)
  const setViewMode = useAppStore((s) => s.setViewMode)

  return (
    <div className="pointer-events-auto flex rounded-lg border border-border-strong bg-panel p-0.5 shadow-lg">
      {(['map', 'table'] as const).map((mode) => (
        <button
          key={mode}
          onClick={() => setViewMode(mode)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
            viewMode === mode ? 'bg-accent text-bg' : 'text-text-muted hover:text-text'
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  )
}
