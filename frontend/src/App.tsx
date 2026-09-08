import { ViewModeToggle } from './components/layout/ViewModeToggle'
import { MapView } from './components/map/MapView'
import { ReportPanel } from './components/report/ReportPanel'
import { TableSidebar } from './components/table/TableSidebar'

export default function App() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg text-text">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-4">
        <span className="text-sm font-semibold tracking-wide">Environmental Assurance Console</span>
        <ViewModeToggle />
      </header>
      <div className="relative flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <MapView />
        </div>
        <TableSidebar />
      </div>
      <ReportPanel />
    </div>
  )
}
