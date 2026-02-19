import { useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, Loader2, XCircle, Clock } from 'lucide-react'
import { fetchOrder, type OrderStatus as Status } from '../api/orders'
import { useCartStore } from '../store/cart'
import Button from '../components/Button'

const STEP_ORDER: Status[] = ['PENDING', 'PAID', 'BUILDING', 'READY']

const STEP_LABELS: Record<Status, string> = {
  PENDING:  'Awaiting payment',
  PAID:     'Payment received',
  BUILDING: 'Building your download',
  READY:    'Ready to download',
  FAILED:   'Failed',
  EXPIRED:  'Expired',
}

const POLL_STATUSES: Status[] = ['PENDING', 'PAID', 'BUILDING']

function StatusStep({ label, done, active }: { label: string; done: boolean; active: boolean }) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${
          done
            ? 'border-sky-500 bg-sky-500'
            : active
              ? 'border-sky-400 bg-transparent animate-pulse'
              : 'border-surface-600 bg-transparent'
        }`}
      >
        {done && <CheckCircle2 size={12} className="text-white" />}
      </span>
      <span className={`text-sm ${done || active ? 'text-content' : 'text-content-muted'}`}>
        {label}
      </span>
    </li>
  )
}

export default function OrderStatus() {
  const { orderId } = useParams<{ orderId: string }>()
  const id = Number(orderId)
  const clear = useCartStore((s) => s.clear)

  const { data: order, error } = useQuery({
    queryKey: ['order', id],
    queryFn: () => fetchOrder(id),
    enabled: !isNaN(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && POLL_STATUSES.includes(status) ? 3000 : false
    },
  })

  // Clear cart when order is confirmed paid
  useEffect(() => {
    if (order?.status === 'PAID' || order?.status === 'READY') {
      clear()
    }
  }, [order?.status, clear])

  if (error) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center">
        <XCircle size={40} className="text-red-400 mx-auto mb-4" />
        <p className="text-gray-400">Order not found or an error occurred.</p>
        <Link to="/" className="mt-6 inline-block">
          <Button variant="secondary">Back to events</Button>
        </Link>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center">
        <Loader2 size={32} className="animate-spin text-sky-500 mx-auto" />
        <p className="text-sm text-gray-400 mt-4">Loading order…</p>
      </div>
    )
  }

  const { status, download_url } = order
  const isFinal = status === 'READY' || status === 'FAILED' || status === 'EXPIRED'
  const currentStepIdx = STEP_ORDER.indexOf(status as Status)

  return (
    <div className="max-w-md mx-auto px-4 sm:px-6 py-16">
      <div className="bg-surface-900 border border-surface-700 rounded-2xl p-8">
        {/* Icon */}
        <div className="flex justify-center mb-6">
          {status === 'READY' ? (
            <CheckCircle2 size={48} className="text-sky-400" />
          ) : status === 'FAILED' ? (
            <XCircle size={48} className="text-red-400" />
          ) : (
            <Clock size={48} className="text-sky-500 animate-pulse" />
          )}
        </div>

          <h1 className="text-xl font-bold text-center text-content mb-1">
          {status === 'READY'
            ? 'Your photos are ready!'
            : status === 'FAILED'
              ? 'Something went wrong'
              : 'Processing your order'}
        </h1>

        <p className="text-sm text-center text-gray-400 mb-8">Order #{id}</p>

        {/* Progress steps */}
        {!isFinal || status === 'READY' ? (
          <ol className="space-y-3 mb-8">
            {STEP_ORDER.map((s, i) => (
              <StatusStep
                key={s}
                label={STEP_LABELS[s]}
                done={currentStepIdx > i || status === 'READY'}
                active={s === status && !isFinal}
              />
            ))}
          </ol>
        ) : null}

        {/* Failed message */}
        {status === 'FAILED' && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2 mb-6">
            Your ZIP could not be built. Please contact support referencing order #{id}.
          </p>
        )}

        {/* Download button */}
        {status === 'READY' && download_url && (
          <a
            href={download_url}
            download
            className="block"
          >
            <Button className="w-full" size="lg">
              <Download size={18} className="mr-2" />
              Download Photos
            </Button>
          </a>
        )}

        {/* Polling indicator */}
        {!isFinal && (
          <p className="text-xs text-gray-500 text-center mt-6">
            Checking automatically every few seconds…
          </p>
        )}

        <div className="mt-6 text-center">
          <Link to="/" className="text-sm text-content-muted hover:text-sky-500 transition-colors">
            Browse more events
          </Link>
        </div>
      </div>
    </div>
  )
}
