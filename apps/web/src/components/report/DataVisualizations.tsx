import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { FireGrowthProjection, FwiKbdiPoint, SarBackscatterPoint } from '../../api/types'
import { formatDate } from '../../lib/format'

const AXIS_TICK = { fontSize: 10, fill: '#8b96a8' }
const TOOLTIP_STYLE = { background: '#171c25', border: '1px solid #303947', fontSize: 11 }

function FireGrowthInset({ projection }: { projection: FireGrowthProjection }) {
  const w = 220
  const h = 140
  const cx = w / 2
  const cy = h / 2
  const rx = Math.min(90, projection.majorAxisKm * 18)
  const ry = Math.min(50, projection.minorAxisKm * 18)
  return (
    <div className="rounded-lg border border-border-strong bg-panel-raised p-3">
      <div className="mb-2 text-xs font-medium text-text-muted">Fire-growth ellipse (estimated)</div>
      <svg width={w} height={h} className="mx-auto block">
        <rect
          x={8}
          y={8}
          width={w - 16}
          height={h - 16}
          rx={4}
          fill="none"
          stroke="#f97316"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <g transform={`translate(${cx} ${cy}) rotate(${projection.orientationDeg})`}>
          <ellipse rx={rx} ry={ry} fill="#ef4444" fillOpacity={0.18} stroke="#ef4444" strokeWidth={1.5} />
        </g>
        <circle cx={cx} cy={cy} r={3} fill="#ef4444" />
      </svg>
      <p className="mt-1 text-[11px] text-text-faint">{projection.note}</p>
    </div>
  )
}

interface DataVisualizationsProps {
  fwiKbdi: FwiKbdiPoint[]
  sarTrend: SarBackscatterPoint[]
  fireGrowth: FireGrowthProjection | null
}

export function DataVisualizations({ fwiKbdi, sarTrend, fireGrowth }: DataVisualizationsProps) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Evidence trends</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-border-strong bg-panel-raised p-3">
          <div className="mb-2 text-xs font-medium text-text-muted">FWI / KBDI / VPD</div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={fwiKbdi} margin={{ left: -12, right: 4, top: 4, bottom: 0 }}>
              <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={(d) => formatDate(d).slice(0, 6)} tick={AXIS_TICK} />
              <YAxis yAxisId="kbdi" tick={AXIS_TICK} width={32} />
              <YAxis yAxisId="idx" orientation="right" tick={AXIS_TICK} width={28} />
              <Tooltip labelFormatter={(d) => formatDate(String(d))} contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line yAxisId="kbdi" type="monotone" dataKey="kbdi" stroke="#22d3ee" dot={false} strokeWidth={2} name="KBDI" />
              <Line yAxisId="idx" type="monotone" dataKey="fwi" stroke="#f97316" dot={false} strokeWidth={2} name="FWI" />
              <Line yAxisId="idx" type="monotone" dataKey="vpd" stroke="#eab308" dot={false} strokeWidth={2} name="VPD" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-lg border border-border-strong bg-panel-raised p-3">
          <div className="mb-2 text-xs font-medium text-text-muted">SAR VH backscatter trend</div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={sarTrend} margin={{ left: -12, right: 4, top: 4, bottom: 0 }}>
              <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={(d) => formatDate(d).slice(0, 6)} tick={AXIS_TICK} />
              <YAxis tick={AXIS_TICK} width={32} />
              <Tooltip labelFormatter={(d) => formatDate(String(d))} contentStyle={TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="vhDb" stroke="#22d3ee" dot strokeWidth={2} name="VH (dB)" />
            </LineChart>
          </ResponsiveContainer>
          {sarTrend.length <= 2 && (
            <p className="mt-1 text-[11px] text-text-faint">
              Only {sarTrend.length} SAR pass(es) in this window — ~6-day revisit cadence, not a UI gap.
            </p>
          )}
        </div>

        {fireGrowth && <FireGrowthInset projection={fireGrowth} />}
      </div>
    </section>
  )
}
