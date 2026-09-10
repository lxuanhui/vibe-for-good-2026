import { forwardRef, type PropsWithChildren, type ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { buildScopePreview } from '../../lib/scope'
import { ScopePreviewMap } from './ScopePreviewMap'

vi.mock('react-map-gl/maplibre', () => ({
  Map: forwardRef<HTMLDivElement, PropsWithChildren<{ children?: ReactNode }>>(({ children }, _ref) => <div data-testid="map">{children}</div>),
  Source: ({ id, children, data }: PropsWithChildren<{ id: string; data?: { features?: unknown[] } }>) => <div data-testid={`source-${id}`} data-feature-count={data?.features?.length}>{children}</div>,
  Layer: ({ id }: { id: string }) => <div data-testid={`layer-${id}`} />,
}))

const scope = buildScopePreview(
  { type: 'Polygon', coordinates: [[[116, -4], [116.5, -4], [116.5, -3.5], [116, -3.5], [116, -4]]] },
  25,
)

test('renders existing Indonesia geography behind the audit scope layers', () => {
  render(<ScopePreviewMap scope={scope} />)

  const map = screen.getByTestId('map')
  const sources = [...map.children].filter((child) => child.getAttribute('data-testid')?.startsWith('source-'))
  expect(sources.map((source) => source.getAttribute('data-testid'))).toEqual([
    'source-indonesia-geographic-context',
    'source-audit-context-buffer',
    'source-audit-boundary',
  ])
  expect(sources[0].getAttribute('data-feature-count')).not.toBe('0')
  expect(screen.getByTestId('layer-indonesia-geographic-context-fill')).toBeTruthy()
  expect(screen.getByTestId('layer-indonesia-geographic-context-line')).toBeTruthy()
})
