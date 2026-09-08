import { ConsoleMap } from './components/console/ConsoleMap'

// The console opens on the map, framed to the audit scope.
//
// Scope-first still holds -- it governs what the map shows, not which screen
// loads first. The map is never a national detection browser: it fits to the
// scope's extent, and the scope-entry flow (#56) opens over it rather than
// gating it. See issue #75 for the reconciliation with #57/#58, which specify
// register-before-map for screening a multi-year history.
export default function App() {
  return (
    <div className="h-full w-full bg-bg text-text">
      <ConsoleMap />
    </div>
  )
}
