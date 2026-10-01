import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import OrderStatus from './OrderStatus'
import { fetchOrder } from '../api/orders'

vi.mock('../api/orders', () => ({ fetchOrder: vi.fn(), prepareOrderZip: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('shows recovery progress rather than a terminal failure while retrying', async () => {
  vi.mocked(fetchOrder).mockResolvedValue({ id: 42, status: 'FAILED', recovery_pending: true, zip: { status: 'NOT_REQUESTED' }, items: [], download_items: [] })
  render(<MemoryRouter initialEntries={['/orders/42']}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/orders/:orderId" element={<OrderStatus />} /></Routes></QueryClientProvider></MemoryRouter>)
  expect(await screen.findByText(/We are retrying interrupted order steps/)).toBeInTheDocument()
  expect(screen.getByText('Processing your order')).toBeInTheDocument()
  expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
})
