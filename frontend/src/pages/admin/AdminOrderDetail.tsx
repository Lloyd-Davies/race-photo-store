import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, ClipboardCopy, Link2, Mail, RefreshCw, RotateCcw } from 'lucide-react'
import Button from '../../components/Button'
import {
  expireAdminOrderDelivery,
  fetchOrderCommunications,
  rebuildAdminOrderZip,
  resetAdminOrderDelivery,
  sendAdminEmail,
  type AdminOrder,
  type CommunicationKind,
} from '../../api/adminOrders'
import type { OrderStatus } from '../../api/orders'

const COMM_KINDS: CommunicationKind[] = ['ORDER_CONFIRMED', 'DOWNLOAD_READY', 'DELIVERY_RESET']

function statusBadge(status: OrderStatus) {
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

function commStatusBadge(status: string) {
  switch (status) {
    case 'SENT':
    case 'DELIVERED':
      return 'bg-green-500/10 text-green-400 border border-green-500/20'
    case 'FAILED':
    case 'BOUNCED':
    case 'BLOCKED':
      return 'bg-red-500/10 text-red-400 border border-red-500/20'
    case 'QUEUED':
    case 'DEFERRED':
      return 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
    default:
      return 'bg-surface-700 text-gray-300 border border-surface-600'
  }
}

interface Props {
  order: AdminOrder
}

function OrderActions({ order }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  const resetMut = useMutation({
    mutationFn: () =>
      resetAdminOrderDelivery(order.id, {
        rotate_token: true,
        days_valid: 30,
        max_downloads: order.max_downloads ?? 5,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
      queryClient.invalidateQueries({ queryKey: ['admin-order', order.id] })
    },
  })

  const rebuildMut = useMutation({
    mutationFn: () => rebuildAdminOrderZip(order.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
      navigate('/admin/orders')
    },
  })

  const expireMut = useMutation({
    mutationFn: () => expireAdminOrderDelivery(order.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
      queryClient.invalidateQueries({ queryKey: ['admin-order', order.id] })
    },
  })

  return (
    <div className="flex flex-wrap gap-2 mt-4">
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
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
          >
            <ClipboardCopy size={13} className="mr-1" />
            {copied ? 'Copied' : 'Copy link'}
          </Button>
        </>
      )}
      <Button size="sm" onClick={() => resetMut.mutate()} loading={resetMut.isPending}>
        <RotateCcw size={13} className="mr-1" />
        Reset delivery
      </Button>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => rebuildMut.mutate()}
        loading={rebuildMut.isPending}
        disabled={order.status === 'PENDING' || order.status === 'BUILDING'}
      >
        <RefreshCw size={13} className="mr-1" />
        Rebuild ZIP
      </Button>
      <Button
        size="sm"
        variant="danger"
        onClick={() => expireMut.mutate()}
        loading={expireMut.isPending}
        disabled={!order.download_url}
      >
        <Ban size={13} className="mr-1" />
        Expire link
      </Button>
    </div>
  )
}

export default function AdminOrderDetail() {
  const { orderId } = useParams<{ orderId: string }>()
  const id = Number(orderId)
  const queryClient = useQueryClient()
  const [sendKind, setSendKind] = useState<CommunicationKind>('ORDER_CONFIRMED')

  const orderData = useQuery({
    queryKey: ['admin-order', id],
    queryFn: async () => {
      const list = await queryClient.fetchQuery({
        queryKey: ['admin-orders'],
        queryFn: () => import('../../api/adminOrders').then((m) => m.fetchAdminOrders({ limit: 500 })),
        staleTime: 30_000,
      })
      const found = list.orders.find((o) => o.id === id)
      if (!found) throw new Error('Order not found')
      return found
    },
  })

  const commsQuery = useQuery({
    queryKey: ['admin-order-comms', id],
    queryFn: () => fetchOrderCommunications(id),
  })

  const sendMut = useMutation({
    mutationFn: () => sendAdminEmail(id, sendKind),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-order-comms', id] }),
  })

  const order = orderData.data

  return (
    <div>
      <Link
        to="/admin/orders"
        className="inline-flex items-center gap-1 text-sm text-content-muted hover:text-content mb-6"
      >
        <ArrowLeft size={14} />
        Back to orders
      </Link>

      <h1 className="text-xl font-bold text-content mb-4">
        Order #{id}
        {order && (
          <span className={`ml-2 text-xs rounded px-2 py-0.5 align-middle ${statusBadge(order.status)}`}>
            {order.status}
          </span>
        )}
      </h1>

      {orderData.isLoading && <p className="text-sm text-content-muted">Loading…</p>}
      {orderData.error && <p className="text-sm text-red-400">{(orderData.error as Error).message}</p>}

      {order && (
        <div className="bg-surface-900 border border-surface-700 rounded-xl p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
            <p className="text-content-muted">Email: <span className="text-content">{order.email || '—'}</span></p>
            <p className="text-content-muted">Event: <span className="text-content">{order.event_slug || '—'}</span></p>
            <p className="text-content-muted">Items: <span className="text-content">{order.item_count}</span></p>
            <p className="text-content-muted">
              Downloads: <span className="text-content">{order.download_count ?? '—'} / {order.max_downloads ?? '—'}</span>
            </p>
            <p className="text-content-muted">
              Created: <span className="text-content">{new Date(order.created_at).toLocaleString()}</span>
            </p>
            {order.paid_at && (
              <p className="text-content-muted">
                Paid: <span className="text-content">{new Date(order.paid_at).toLocaleString()}</span>
              </p>
            )}
            {order.expires_at && (
              <p className="text-content-muted">
                Link expires: <span className="text-content">{new Date(order.expires_at).toLocaleString()}</span>
              </p>
            )}
          </div>
          <OrderActions order={order} />
        </div>
      )}

      {/* Communications section */}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-content">Email history</h2>
        <div className="flex items-center gap-2">
          <select
            value={sendKind}
            onChange={(e) => setSendKind(e.target.value as CommunicationKind)}
            className="bg-surface-800 border border-surface-600 rounded text-xs text-content px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            {COMM_KINDS.map((k) => (
              <option key={k} value={k}>{k.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <Button size="sm" onClick={() => sendMut.mutate()} loading={sendMut.isPending}>
            <Mail size={13} className="mr-1" />
            Send email
          </Button>
        </div>
      </div>

      {sendMut.error && (
        <p className="text-xs text-red-400 mb-3">{(sendMut.error as Error).message}</p>
      )}

      {commsQuery.isLoading && <p className="text-sm text-content-muted">Loading history…</p>}
      {commsQuery.error && <p className="text-sm text-red-400">{(commsQuery.error as Error).message}</p>}

      {commsQuery.data && commsQuery.data.length === 0 && (
        <p className="text-sm text-content-muted">No emails sent for this order yet.</p>
      )}

      {commsQuery.data && commsQuery.data.length > 0 && (
        <div className="bg-surface-900 border border-surface-700 rounded-xl divide-y divide-surface-700">
          {commsQuery.data.map((comm) => (
            <div key={comm.id} className="px-4 py-3 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2 items-start">
              <div>
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-xs font-medium text-content">{comm.kind.replace(/_/g, ' ')}</span>
                  <span className={`text-xs rounded px-1.5 py-0.5 ${commStatusBadge(comm.status)}`}>
                    {comm.status}
                  </span>
                  {comm.initiated_by && (
                    <span className="text-xs text-content-muted">via {comm.initiated_by}</span>
                  )}
                </div>
                <p className="text-xs text-content-muted">{comm.recipient_email} — {comm.subject}</p>
                {comm.error_message && (
                  <p className="text-xs text-red-400 mt-1">{comm.error_message}</p>
                )}
              </div>
              <div className="text-xs text-content-muted text-right whitespace-nowrap">
                <p>{new Date(comm.created_at).toLocaleString()}</p>
                {comm.sent_at && <p>Sent: {new Date(comm.sent_at).toLocaleString()}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
