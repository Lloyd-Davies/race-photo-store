import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { HistoricalRecoveryPreview, OrderRecovery } from './OrderRecovery'
import { apiGet, apiPost } from '../api/client'

vi.mock('../api/client', () => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

function show(element: React.ReactNode) {
  return render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{element}</QueryClientProvider></MemoryRouter>)
}

it('keeps historical preview read-only and links to explicit order selection', async () => {
  vi.mocked(apiGet).mockResolvedValue({ candidates: [{ order_id: 42, steps: ['Verify payment'] }], next_after_id: null })
  show(<HistoricalRecoveryPreview />)
  expect(apiGet).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Preview older orders needing recovery'))
  expect(await screen.findByText('Order #42')).toHaveAttribute('href', '/admin/orders/42')
  expect(apiPost).not.toHaveBeenCalled()
})

it('shows failed steps and only retries after explicit selection', async () => {
  vi.mocked(apiGet).mockResolvedValue({ steps: ['Resume customer-requested ZIP'], jobs: [{ kind: 'zip', status: 'REVIEW', attempts: 5, error: 'Original unavailable' }] })
  vi.mocked(apiPost).mockResolvedValue({})
  show(<OrderRecovery orderId={42} />)
  expect(await screen.findByText('Original unavailable')).toBeInTheDocument()
  expect(apiPost).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Retry listed steps safely'))
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/admin/orders/42/recovery'))
})

it('blocks retries when access or refunds require review', async () => {
  vi.mocked(apiGet).mockResolvedValue({ excluded_reason: 'Refund activity requires review', steps: ['Verify payment'], jobs: [] })
  show(<OrderRecovery orderId={42} />)
  expect(await screen.findByText('Refund activity requires review')).toBeInTheDocument()
  expect(screen.queryByText('Retry listed steps safely')).not.toBeInTheDocument()
})
