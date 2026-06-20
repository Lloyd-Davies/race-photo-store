import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  Link2,
  RefreshCw,
  RotateCcw,
  Search,
} from 'lucide-react'
import Button from '../../components/Button'
import { fetchAdminEvents } from '../../api/events'
import {
  expireAdminOrderDelivery,
  exportAdminOrders,
  fetchAdminOrders,
  rebuildAdminOrderZip,
  resetAdminOrderDelivery,
  type AdminOrder,
  type AdminOrderQuery,
  type DeliveryZipStatus,
} from '../../api/adminOrders'
import type { OrderStatus } from '../../api/orders'
import { formatMoney } from '../../utils/money'

const ORDER_STATUSES: Array<OrderStatus | 'ALL'> = [
  'ALL',
  'PENDING',
  'PAID',
  'BUILDING',
  'READY',
  'FAILED',
  'EXPIRED',
]

const ZIP_STATUSES: Array<DeliveryZipStatus | 'ALL'> = [
  'ALL',
  'NOT_REQUESTED',
  'BUILDING',
  'READY',
  'EXPIRED',
  'FAILED',
]

function badgeClass(status?: string) {
  switch (status) {
    case 'READY':
    case 'SENT':
    case 'DELIVERED':
      return 'border-green-500/20 bg-green-500/10 text-green-400'
    case 'FAILED':
    case 'BOUNCED':
    case 'BLOCKED':
      return 'border-red-500/20 bg-red-500/10 text-red-400'
    case 'BUILDING':
    case 'PENDING':
    case 'QUEUED':
      return 'border-sky-500/20 bg-sky-500/10 text-sky-400'
    case 'EXPIRED':
      return 'border-amber-500/20 bg-amber-500/10 text-amber-400'
    default:
      return 'border-surface-600 bg-surface-800 text-content-muted'
  }
}

function dateStart(value: string) {
  return value ? `${value}T00:00:00Z` : undefined
}

function dateEnd(value: string) {
  return value ? `${value}T23:59:59Z` : undefined
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function OrderActions({
  order,
  copiedOrder,
  setCopiedOrder,
}: {
  order: AdminOrder
  copiedOrder: number | null
  setCopiedOrder: (orderId: number | null) => void
}) {
  const queryClient = useQueryClient()

  const resetMut = useMutation({
    mutationFn: () =>
      resetAdminOrderDelivery(order.id, {
        rotate_token: true,
        days_valid: 30,
        max_downloads: order.max_downloads ?? 5,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  const rebuildMut = useMutation({
    mutationFn: () => rebuildAdminOrderZip(order.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  const expireMut = useMutation({
    mutationFn: () => expireAdminOrderDelivery(order.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
  })

  return (
    <div className="flex gap-1.5 overflow-x-auto md:justify-end md:overflow-visible">
      {order.download_url && (
        <>
          <a href={order.download_url} target="_blank" rel="noreferrer" title="Open download link">
            <Button size="sm" variant="ghost" aria-label="Open download link">
              <Link2 size={14} />
            </Button>
          </a>
          <Button
            size="sm"
            variant="ghost"
            title="Copy download link"
            aria-label="Copy download link"
            onClick={async () => {
              await navigator.clipboard.writeText(order.download_url as string)
              setCopiedOrder(order.id)
              setTimeout(() => setCopiedOrder(null), 1500)
            }}
          >
            <ClipboardCopy size={14} />
            {copiedOrder === order.id && <span className="ml-1">Copied</span>}
          </Button>
        </>
      )}
      <Button
        size="sm"
        variant="ghost"
        title="Reset delivery"
        aria-label="Reset delivery"
        onClick={() => resetMut.mutate()}
        loading={resetMut.isPending}
      >
        <RotateCcw size={14} />
      </Button>
      <Button
        size="sm"
        variant="ghost"
        title="Rebuild ZIP"
        aria-label="Rebuild ZIP"
        onClick={() => rebuildMut.mutate()}
        loading={rebuildMut.isPending}
        disabled={order.status === 'PENDING' || order.status === 'BUILDING' || order.zip_status === 'BUILDING'}
      >
        <RefreshCw size={14} />
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-red-400 hover:text-red-300"
        title="Expire delivery"
        aria-label="Expire delivery"
        onClick={() => expireMut.mutate()}
        loading={expireMut.isPending}
        disabled={!order.download_url}
      >
        <Ban size={14} />
      </Button>
    </div>
  )
}

export default function AdminOrders() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<OrderStatus | 'ALL'>('ALL')
  const [zipStatus, setZipStatus] = useState<DeliveryZipStatus | 'ALL'>('ALL')
  const [eventId, setEventId] = useState<number | 'ALL'>('ALL')
  const [createdFrom, setCreatedFrom] = useState('')
  const [createdTo, setCreatedTo] = useState('')
  const [page, setPage] = useState(1)
  const [copiedOrder, setCopiedOrder] = useState<number | null>(null)

  const queryParams: AdminOrderQuery = useMemo(() => ({
    status,
    zip_status: zipStatus,
    event_id: eventId,
    q: search.trim() || undefined,
    page,
    page_size: 50,
    sort: 'id',
    direction: 'desc',
    created_from: dateStart(createdFrom),
    created_to: dateEnd(createdTo),
  }), [createdFrom, createdTo, eventId, page, search, status, zipStatus])

  const eventsQuery = useQuery({
    queryKey: ['admin-events'],
    queryFn: fetchAdminEvents,
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-orders', queryParams],
    queryFn: () => fetchAdminOrders(queryParams),
  })

  const exportMut = useMutation({
    mutationFn: () => exportAdminOrders(queryParams),
    onSuccess: (blob) => downloadBlob(blob, 'admin-orders.csv'),
  })

  const orders = data?.orders ?? []
  const total = data?.total ?? 0
  const pageSize = data?.page_size ?? 50
  const pages = Math.max(1, Math.ceil(total / pageSize))

  function resetFilters() {
    setSearch('')
    setStatus('ALL')
    setZipStatus('ALL')
    setEventId('ALL')
    setCreatedFrom('')
    setCreatedTo('')
    setPage(1)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl font-bold text-content">Orders</h1>
          <p className="text-xs text-content-muted">{total} matching orders</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => exportMut.mutate()} loading={exportMut.isPending}>
          <Download size={14} className="mr-1" />
          Export CSV
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-lg border border-surface-700 bg-surface-900 p-4 xl:grid-cols-[1.5fr_repeat(5,minmax(0,1fr))_auto]">
        <label className="relative block">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search orders, email, event, token"
            className="w-full rounded-md border border-surface-600 bg-surface-800 py-2 pl-9 pr-3 text-sm text-content placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </label>

        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value as OrderStatus | 'ALL'); setPage(1) }}
          className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {ORDER_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>

        <select
          value={zipStatus}
          onChange={(e) => { setZipStatus(e.target.value as DeliveryZipStatus | 'ALL'); setPage(1) }}
          className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {ZIP_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>

        <select
          value={eventId}
          onChange={(e) => { setEventId(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value)); setPage(1) }}
          className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          <option value="ALL">All events</option>
          {(eventsQuery.data ?? []).map((event) => (
            <option key={event.id} value={event.id}>{event.name}</option>
          ))}
        </select>

        <input
          type="date"
          value={createdFrom}
          onChange={(e) => { setCreatedFrom(e.target.value); setPage(1) }}
          className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
        />

        <input
          type="date"
          value={createdTo}
          onChange={(e) => { setCreatedTo(e.target.value); setPage(1) }}
          className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
        />

        <Button size="sm" variant="ghost" onClick={resetFilters}>
          Reset
        </Button>
      </div>

      {isLoading && <p className="text-sm text-content-muted">Loading orders...</p>}
      {error && <p className="text-sm text-red-400">{(error as Error).message}</p>}
      {exportMut.error && <p className="text-sm text-red-400">{(exportMut.error as Error).message}</p>}

      {!isLoading && !error && orders.length === 0 && (
        <p className="text-sm text-content-muted">No orders match your filters.</p>
      )}

      {orders.length > 0 && (
        <>
          <div className="hidden overflow-x-auto rounded-lg border border-surface-700 bg-surface-900 lg:block">
            <table className="w-full min-w-[1120px] text-left text-sm">
              <thead className="border-b border-surface-700 text-xs text-content-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Order</th>
                  <th className="px-4 py-3 font-medium">Customer</th>
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium">Paid</th>
                  <th className="px-4 py-3 font-medium text-right">Items</th>
                  <th className="px-4 py-3 font-medium text-right">Collected</th>
                  <th className="px-4 py-3 font-medium">Promotion</th>
                  <th className="px-4 py-3 font-medium">Downloads</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-700">
                {orders.map((order) => (
                  <tr key={order.id} className="align-top">
                    <td className="px-4 py-3">
                      <Link to={`/admin/orders/${order.id}`} className="font-semibold text-content hover:text-sky-400">
                        #{order.id}
                      </Link>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <span className={`rounded border px-1.5 py-0.5 text-[11px] ${badgeClass(order.status)}`}>
                          {order.status}
                        </span>
                        <span className={`rounded border px-1.5 py-0.5 text-[11px] ${badgeClass(order.zip_status)}`}>
                          {order.zip_status ?? 'NO ZIP'}
                        </span>
                      </div>
                    </td>
                    <td className="max-w-[220px] truncate px-4 py-3 text-content">{order.email || '-'}</td>
                    <td className="px-4 py-3 text-content-muted">{order.event_slug || '-'}</td>
                    <td className="px-4 py-3 text-content-muted">{new Date(order.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-content-muted">{order.paid_at ? new Date(order.paid_at).toLocaleString() : '-'}</td>
                    <td className="px-4 py-3 text-right text-content">{order.item_count}</td>
                    <td className="px-4 py-3 text-right text-content">
                      {order.collected_pence == null ? <span className="text-amber-400">Unsynced</span> : formatMoney(order.collected_pence, order.currency)}
                    </td>
                    <td className="max-w-[140px] truncate px-4 py-3 text-content-muted">{order.promotion_codes.join(', ') || '-'}</td>
                    <td className="px-4 py-3 text-content-muted">
                      {order.download_count ?? '-'} / {order.max_downloads ?? '-'}
                    </td>
                    <td className="px-4 py-3">
                      <OrderActions order={order} copiedOrder={copiedOrder} setCopiedOrder={setCopiedOrder} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="space-y-3 lg:hidden">
            {orders.map((order) => (
              <div key={order.id} className="rounded-lg border border-surface-700 bg-surface-900 p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link to={`/admin/orders/${order.id}`} className="font-semibold text-content hover:text-sky-400">
                      Order #{order.id}
                    </Link>
                    <p className="truncate text-xs text-content-muted">{order.email || '-'}</p>
                  </div>
                  <span className="text-sm font-semibold text-content">
                    {order.collected_pence == null ? 'Unsynced' : formatMoney(order.collected_pence, order.currency)}
                  </span>
                </div>
                <div className="mb-3 grid grid-cols-2 gap-2 text-xs text-content-muted">
                  <span>Event <span className="text-content">{order.event_slug || '-'}</span></span>
                  <span>Items <span className="text-content">{order.item_count}</span></span>
                  <span>Downloads <span className="text-content">{order.download_count ?? '-'} / {order.max_downloads ?? '-'}</span></span>
                  <span>Promo <span className="text-content">{order.promotion_codes.join(', ') || '-'}</span></span>
                  <span>{new Date(order.created_at).toLocaleDateString()}</span>
                </div>
                <div className="mb-3 flex flex-wrap gap-1">
                  <span className={`rounded border px-1.5 py-0.5 text-[11px] ${badgeClass(order.status)}`}>{order.status}</span>
                  <span className={`rounded border px-1.5 py-0.5 text-[11px] ${badgeClass(order.zip_status)}`}>{order.zip_status ?? 'NO ZIP'}</span>
                </div>
                <OrderActions order={order} copiedOrder={copiedOrder} setCopiedOrder={setCopiedOrder} />
              </div>
            ))}
          </div>
        </>
      )}

      {total > 0 && (
        <div className="flex items-center justify-between gap-3">
          <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            <ChevronLeft size={14} className="mr-1" />
            Prev
          </Button>
          <span className="text-sm text-content-muted">Page {page} of {pages}</span>
          <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => Math.min(pages, value + 1))}>
            Next
            <ChevronRight size={14} className="ml-1" />
          </Button>
        </div>
      )}
    </div>
  )
}
