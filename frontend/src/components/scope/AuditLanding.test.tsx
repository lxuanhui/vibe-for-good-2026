import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { fetchLiveFirmsDetections } from '../../api/client'
import { AuditLanding } from './AuditLanding'

vi.mock('../../api/client', () => ({
  fetchLiveFirmsDetections: vi.fn(),
}))

vi.mock('react-map-gl/maplibre', () => ({
  Layer: () => null,
  Map: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Source: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

const fetchLiveFirmsDetectionsMock = vi.mocked(fetchLiveFirmsDetections)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

test('renders the returned FIRMS status as red inline text without card chrome', async () => {
  fetchLiveFirmsDetectionsMock.mockResolvedValue({
    status: 'ready',
    sensor: 'VIIRS',
    windowHours: 24,
    fetchedAt: '2026-09-10T00:00:00Z',
    detections: { type: 'FeatureCollection', features: [] },
  })

  render(<AuditLanding onStartAudit={vi.fn()} onOpenContext={vi.fn()} />)

  const status = await screen.findByRole('status')
  await waitFor(() => expect(status.textContent).toContain('NO DETECTIONS RETURNED'))

  expect(status.className).toContain('text-status-urgent')
  expect(status.className).not.toMatch(/rounded|border|bg-|p-3/)
  expect(status.textContent).toContain('No thermal detections were returned for the past 24 hours.')
})
