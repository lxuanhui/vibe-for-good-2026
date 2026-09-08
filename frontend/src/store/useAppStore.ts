import { create } from 'zustand'
import type { OverlayLayerId, RasterLayerId } from '../api/types'
import { TIMELINE_DATES } from '../api/fixtures/dates'

export type ViewMode = 'map' | 'table' | 'report'

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

  reportEventId: string | null
  openReport: (id: string) => void
  closeReport: () => void

  auditId: string | null
  registerSelection: string[]
  setAuditSession: (auditId: string, selection?: string[]) => void
  toggleRegisterSelection: (id: string) => void
  clearRegisterSelection: () => void
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

  reportEventId: null,
  openReport: (id) => set({ reportEventId: id }),
  closeReport: () => set({ reportEventId: null }),

  auditId: null,
  registerSelection: [],
  setAuditSession: (auditId, selection = []) => set({ auditId, registerSelection: selection, viewMode: 'table' }),
  toggleRegisterSelection: (id) =>
    set((s) => ({ registerSelection: s.registerSelection.includes(id) ? s.registerSelection.filter((value) => value !== id) : [...s.registerSelection, id] })),
  clearRegisterSelection: () => set({ registerSelection: [] }),
}))
