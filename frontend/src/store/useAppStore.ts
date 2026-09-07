import { create } from 'zustand'
import type { OverlayLayerId, RasterLayerId } from '../api/types'
import { TIMELINE_DATES } from '../api/fixtures/dates'

export type ViewMode = 'map' | 'table'

type LayerId = OverlayLayerId | RasterLayerId

interface AppState {
  viewMode: ViewMode
  setViewMode: (mode: ViewMode) => void

  selectedEventId: string | null
  selectEvent: (id: string | null) => void

  activeDate: string
  setActiveDate: (date: string) => void
  isPlaying: boolean
  togglePlaying: () => void

  layerVisibility: Record<LayerId, boolean>
  toggleLayer: (layer: LayerId) => void

  pipelineFirmsVisible: boolean
  togglePipelineFirms: () => void

  reportEventId: string | null
  openReport: (id: string) => void
  closeReport: () => void
}

export const useAppStore = create<AppState>((set) => ({
  viewMode: 'map',
  setViewMode: (mode) => set({ viewMode: mode }),

  selectedEventId: null,
  selectEvent: (id) => set({ selectedEventId: id }),

  activeDate: TIMELINE_DATES[TIMELINE_DATES.length - 1],
  setActiveDate: (date) => set({ activeDate: date }),
  isPlaying: false,
  togglePlaying: () => set((s) => ({ isPlaying: !s.isPlaying })),

  layerVisibility: {
    firms: true,
    'sar-backscatter': false,
    khg: true,
    concessions: false,
    'fire-complex-links': true,
    's2-quicklook': false,
    'sar-visualization': false,
  },
  toggleLayer: (layer) =>
    set((s) => ({ layerVisibility: { ...s.layerVisibility, [layer]: !s.layerVisibility[layer] } })),

  pipelineFirmsVisible: false,
  togglePipelineFirms: () => set((s) => ({ pipelineFirmsVisible: !s.pipelineFirmsVisible })),

  reportEventId: null,
  openReport: (id) => set({ reportEventId: id }),
  closeReport: () => set({ reportEventId: null }),
}))
