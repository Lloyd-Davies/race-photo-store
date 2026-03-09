import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, RotateCcw, Search, ClipboardCopy, RefreshCw, Ban, ChevronRight } from 'lucide-react'
import Button from '../../components/Button'
import {
  expireAdminOrderDelivery,
  fetchAdminOrders,
  rebuildAdminOrderZip,
  resetAdminOrderDelivery,
  type AdminOrder,
} from '../../api/adminOrders'
import type { OrderStatus } from '../../api/orders'

const ORDER_STATUSES: Array<OrderStatus | 'ALL'> = [
  'ALL',
  'PENDING',
  'PAID',
  'BUILDING',
  'READY',
  'FAILED',
  'EXPIRED',
]

function statusClass(status: OrderStatus) {
  switch (status) {
    case 'READY':
      return 'bg-green-500/10 text-green-400 border border-green-500/20'
    case 'FAILED':
      return 'bg-red-500/10 text-red-400 border border-red-500/20'
    case 'BUILDING':
      return 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
    default:
      return 'bg-surface-700 text-gray-300 border border-surface-600'
  }
}

export default function AdminOrders() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<OrderStatus | 'ALL'>('ALL')
  const [copiedOrder, setCopiedOrder] = useState<number | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-orders', status, search],
    queryFn: () => fetchAdminOrders({ status, q: search.trim() || undefined, limit: 200 }),
  })

  const resetMut = useMutation({
    mutationFn: (order: AdminOrder) =>
      resetAdminOrderDelivery(order.id, {
        rotate_token: true,
        days_valid: 30,
        max_downloads: order.max_downloads ?? 5,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  const rebuildMut = useMutation({
    mutationFn: (orderId: number) => rebuildAdminOrderZip(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  const expireMut = useMutation({
    mutationFn: (orderId: number) => expireAdminOrderDelivery(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  const orders = data?.orders ?? []
  const sorted = useMemo(() => [...orders].sort((a, b) => b.id - a.id), [orders])

  return (
    <div>
      <div className="flex items-center justify-between mb-6 gap-3">
        <h1 className="text-xl font-bold text-content">Orders</h1>
      </div>

      <div className="bg-surface-900 border border-surface-700 rounded-xl p-4 mb-6 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
        <label className="relative block">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by order ID, email, event slug, or token"
            className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content pl-9 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
          />
        </label>

        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as OrderStatus | 'ALL')}
          className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-content-muted">Loading orders…</p>}
      {error && <p className="text-sm text-red-400">{(error as Error).message}</p>}

      {!isLoading && !error && sorted.length === 0 && (
        <p className="text-sm text-content-muted">No orders match your filters.</p>
      )}

      <div className="space-y-3">
        {sorted.map((order) => (
          <div key={order.id} className="bg-surface-900 border border-surface-700 rounded-xl p-4">
            <div className="flex flex-wrap items-center gap-2 justify-between mb-3">
              <div className="flex items-center gap-2">
                <Link
                  to={`/admin/orders/${order.id}`}
                  className="text-sm font-semibold text-content hover:text-sky-400"
                >
                  Order #{order.id}
                </Link>
                <span className={`text-xs rounded px-2 py-0.5 ${statusClass(order.status)}`}>
                  {order.status}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-content-muted">{new Date(order.created_at).toLocaleString()}</span>
                <Link to={`/admin/orders/${order.id}`} className="text-content-muted hover:text-content">
                  <ChevronRight size={14} />
                </Link>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm mb-4">
              <p className="text-content-muted">Email: <span className="text-content">{order.email || '—'}</span></p>
              <p className="text-content-muted">Event: <span className="text-content">{order.event_slug || '—'}</span></p>
              <p className="text-content-muted">Items: <span className="text-content">{order.item_count}</span></p>
              <p className="text-content-muted">
                Downloads: <span className="text-content">{order.download_count ?? '—'} / {order.max_downloads ?? '—'}</span>
              </p>
            </div>

            <div className="flex gap-2 overflow-x-auto pb-0.5 md:flex-wrap md:overflow-visible">
              {order.download_url && (
                <>
                  <a href={order.download_url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="secondary">
                      <Link2 size={13} className="mr-1" />
                      Open link
                    </Button>
                  </a>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      await navigator.clipboard.writeText(order.download_url as string)
                      setCopiedOrder(order.id)
                      setTimeout(() => setCopiedOrder(null), 1500)
                    }}
                  >
                    <ClipboardCopy size={13} className="mr-1" />
                    {copiedOrder === order.id ? 'Copied' : 'Copy link'}
                  </Button>
                </>
              )}

              <Button
                size="sm"
                onClick={() => resetMut.mutate(order)}
                loading={resetMut.isPending}
              >
                <RotateCcw size={13} className="mr-1" />
                Reset delivery access
              </Button>

              <Button
                size="sm"
                variant="secondary"
                onClick={() => rebuildMut.mutate(order.id)}
                loading={rebuildMut.isPending}
                disabled={order.status === 'PENDING' || order.status === 'BUILDING'}
              >
                <RefreshCw size={13} className="mr-1" />
                Rebuild ZIP
              </Button>

              <Button
                size="sm"
                variant="danger"
                onClick={() => expireMut.mutate(order.id)}
                loading={expireMut.isPending}
                disabled={!order.download_url}
              >
                <Ban size={13} className="mr-1" />
                Expire link
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}