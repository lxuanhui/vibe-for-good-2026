import type { ReactNode } from 'react'
import type { OverlayLayerId, RasterLayerId } from '../../api/types'
import { PIPELINE_FIRMS_DATE_RANGE } from '../../api/fixtures/pipelineFirms'
import { KHG_CLASSIFICATION_COLORS, LAYER_COLORS, PIPELINE_FIRMS_COLOR } from '../../lib/layerColors'
import { useAppStore } from '../../store/useAppStore'
import { Toggle } from '../ui/Toggle'

function Dot({ color }: { color: string }) {
  return <span className="block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
}

function DashSwatch({ color }: { color: string }) {
  return (
    <span
      className="block h-0 w-3 shrink-0 border-t-2"
      style={{ borderColor: color, borderStyle: 'dashed' }}
    />
  )
}

function DualDot({ colorA, colorB }: { colorA: string; colorB: string }) {
  return (
    <span className="flex shrink-0 items-center gap-0.5">
      <Dot color={colorA} />
      <Dot color={colorB} />
    </span>
  )
}

const GEOJSON_LAYERS: { id: OverlayLayerId; label: string; swatch: ReactNode; caption?: string }[] = [
  { id: 'firms', label: 'FIRMS thermal hotspots', swatch: <Dot color={LAYER_COLORS.firms} /> },
  { id: 'sar-backscatter', label: 'SAR backscatter (VH drop)', swatch: <Dot color={LAYER_COLORS['sar-backscatter']} /> },
  {
    id: 'khg',
    label: 'Peat hydrology (KHG)',
    swatch: <DualDot colorA={KHG_CLASSIFICATION_COLORS.protected_dome} colorB={KHG_CLASSIFICATION_COLORS.production_zone} />,
    caption: 'Orange = protected dome · Blue = production zone',
  },
  { id: 'concessions', label: 'Concessions', swatch: <Dot color={LAYER_COLORS.concessions} /> },
  {
    id: 'fire-complex-links',
    label: 'Fire-complex links',
    swatch: <DashSwatch color={LAYER_COLORS['fire-complex-links']} />,
  },
]

const RASTER_LAYERS: { id: RasterLayerId; label: string }[] = [
  { id: 's2-quicklook', label: 'Sentinel-2 quicklook' },
  { id: 'sar-visualization', label: 'SAR visualization' },
]

export function LayerControlPanel() {
  const layerVisibility = useAppStore((s) => s.layerVisibility)
  const toggleLayer = useAppStore((s) => s.toggleLayer)
  const pipelineFirmsVisible = useAppStore((s) => s.pipelineFirmsVisible)
  const togglePipelineFirms = useAppStore((s) => s.togglePipelineFirms)

  return (
    <div className="pointer-events-auto w-64 rounded-lg border border-border-strong bg-panel/95 p-3 shadow-lg backdrop-blur">
      <div className="mb-2 text-[11px] font-semibold tracking-wide text-text-faint uppercase">Layers</div>
      <div className="space-y-1">
        {GEOJSON_LAYERS.map((l) => (
          <Toggle
            key={l.id}
            label={l.label}
            swatch={l.swatch}
            caption={l.caption}
            checked={layerVisibility[l.id]}
            onChange={() => toggleLayer(l.id)}
          />
        ))}
      </div>
      <div className="my-2 border-t border-border" />
      <div className="mb-2 text-[11px] font-semibold tracking-wide text-text-faint uppercase">Pipeline data (real)</div>
      <div className="space-y-1">
        <Toggle
          label="NASA FIRMS pull (21,519 pts)"
          caption={`${PIPELINE_FIRMS_DATE_RANGE[0]} → ${PIPELINE_FIRMS_DATE_RANGE[1]} · not linked to timeline`}
          swatch={<Dot color={PIPELINE_FIRMS_COLOR} />}
          checked={pipelineFirmsVisible}
          onChange={togglePipelineFirms}
        />
      </div>
      <div className="my-2 border-t border-border" />
      <div className="space-y-0.5">
        {RASTER_LAYERS.map((l) => (
          <Toggle
            key={l.id}
            label={l.label}
            checked={false}
            disabled
            disabledHint="No tile data in mock mode"
            onChange={() => {}}
          />
        ))}
      </div>
      <div className="my-2 border-t border-border" />
      <div className="text-[11px] font-semibold tracking-wide text-text-faint uppercase">Event markers</div>
      <div className="mt-1.5 space-y-1 text-xs text-text-muted">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3 shrink-0 items-center justify-center">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-urgent opacity-60" />
            <span className="relative block h-3 w-3 rounded-full bg-status-urgent" />
          </span>
          Active detection on current pass
        </div>
        <div className="flex items-center gap-2">
          <span className="block h-3 w-3 shrink-0 rounded-full border-2 border-status-quiet bg-bg/70" />
          Monitored, no active detection
        </div>
      </div>
    </div>
  )
}
