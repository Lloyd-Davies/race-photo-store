import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  Users,
  ShoppingCart,
  Images,
  ReceiptText,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import Button from '../../components/Button'
import { fetchAdminEvents } from '../../api/events'
import {
  fetchAdminMetrics,
  type AdminMetrics,
  type AdminMetricsRange,
  type AdminMoneyMetric,
} from '../../api/adminMetrics'
import { reconcileAdminStripeOrders } from '../../api/adminOrders'
import { formatMoney } from '../../utils/money'

const RANGES: Array<{ value: AdminMetricsRange; label: string }> = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: '365d', label: '365 days' },
  { value: 'all', label: 'All time' },
]

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa', '#14b8a6']

function moneySum(money: AdminMoneyMetric[], key: keyof AdminMoneyMetric) {
  return money.reduce((sum, item) => sum + Number(item[key] || 0), 0)
}

function primaryCurrency(metrics?: AdminMetrics) {
  return metrics?.money[0]?.currency ?? 'GBP'
}

function formatMetricMoney(metrics: AdminMetrics | undefined, key: keyof AdminMoneyMetric) {
  const currency = primaryCurrency(metrics)
  return formatMoney(moneySum(metrics?.money ?? [], key), currency)
}

function compactDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
  })
}

function statusClass(value: string) {
  const key = value.toUpperCase()
  if (key.includes('FAILED') || key.includes('ERROR') || key.includes('BLOCKED')) {
    return 'border-red-500/30 bg-red-500/10 text-red-400'
  }
  if (key.includes('READY') || key.includes('SENT') || key.includes('DELIVERED') || key.includes('PAID')) {
    return 'border-green-500/30 bg-green-500/10 text-green-400'
  }
  if (key.includes('PENDING') || key.includes('BUILDING') || key.includes('QUEUED')) {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-400'
  }
  return 'border-surface-600 bg-surface-800 text-content-muted'
}

function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-surface-700 bg-surface-900 p-4 ${className}`}>
      {children}
    </section>
  )
}

function SectionTitle({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold text-content">{title}</h2>
      {action}
    </div>
  )
}

function Kpi({
  label,
  value,
  icon,
}: {
  label: string
  value: string | number
  icon: ReactNode
}) {
  return (
    <div className="rounded-lg border border-surface-700 bg-surface-900 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-xs text-content-muted">{label}</span>
        <span className="text-content-muted">{icon}</span>
      </div>
      <p className="truncate text-xl font-semibold text-content">{value}</p>
    </div>
  )
}

function MoneyTable({ metrics }: { metrics: AdminMetrics }) {
  return (
    <Panel>
      <SectionTitle title="Currency totals" />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="border-b border-surface-700 text-xs text-content-muted">
            <tr>
              <th className="py-2 pr-3 font-medium">Currency</th>
              <th className="py-2 pr-3 font-medium">Gross</th>
              <th className="py-2 pr-3 font-medium">Pending</th>
              <th className="py-2 pr-3 font-medium">Discount</th>
              <th className="py-2 pr-3 font-medium">AOV</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-700">
            {metrics.money.map((row) => (
              <tr key={row.currency}>
                <td className="py-2 pr-3 font-medium text-content">{row.currency}</td>
                <td className="py-2 pr-3 text-content">{formatMoney(row.gross_sales_pence, row.currency)}</td>
                <td className="py-2 pr-3 text-content-muted">{formatMoney(row.pending_value_pence, row.currency)}</td>
                <td className="py-2 pr-3 text-content-muted">{formatMoney(row.discount_pence, row.currency)}</td>
                <td className="py-2 pr-3 text-content-muted">{formatMoney(row.average_order_value_pence, row.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

export default function AdminDashboard() {
  const queryClient = useQueryClient()
  const [range, setRange] = useState<AdminMetricsRange>('30d')
  const [eventId, setEventId] = useState<number | 'ALL'>('ALL')

  const eventsQuery = useQuery({
    queryKey: ['admin-events'],
    queryFn: fetchAdminEvents,
  })

  const metricsQuery = useQuery({
    queryKey: ['admin-metrics', range, eventId],
    queryFn: () => fetchAdminMetrics({ range, event_id: eventId }),
    refetchInterval: 30000,
  })

  const reconcileMut = useMutation({
    mutationFn: () => reconcileAdminStripeOrders({ older_than_minutes: 15, limit: 25 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-metrics'] })
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
    },
  })

  const metrics = metricsQuery.data
  const currency = primaryCurrency(metrics)

  const trendRows = useMemo(
    () =>
      (metrics?.daily_trends ?? []).map((row) => ({
        date: compactDate(row.date),
        orders: row.order_count,
        paid: row.paid_order_count,
        items: row.item_count,
        revenue: (row.revenue_by_currency[currency] ?? 0) / 100,
      })),
    [metrics?.daily_trends, currency],
  )

  const statusRows = metrics?.status_breakdown ?? []
  const deliveryRows = metrics?.delivery_health ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-xl font-bold text-content">Dashboard</h1>
          <p className="text-xs text-content-muted">
            {metrics ? `Updated ${new Date(metrics.generated_at).toLocaleTimeString()}` : 'Loading metrics'}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as AdminMetricsRange)}
            className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            {RANGES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
          <select
            value={eventId}
            onChange={(e) => setEventId(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
            className="rounded-md border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="ALL">All events</option>
            {(eventsQuery.data ?? []).map((event) => (
              <option key={event.id} value={event.id}>{event.name}</option>
            ))}
          </select>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => reconcileMut.mutate()}
            loading={reconcileMut.isPending}
          >
            <RefreshCw size={14} className="mr-1" />
            Reconcile Stripe
          </Button>
        </div>
      </div>

      {metricsQuery.error && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {(metricsQuery.error as Error).message}
        </p>
      )}
      {reconcileMut.data && (
        <p className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-300">
          {reconcileMut.data.message}
        </p>
      )}

      {metrics && (
        <>
          {metrics.mixed_currency && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
              Mixed currencies are present. Monetary totals are grouped by currency.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <Kpi label="Gross sales" value={formatMetricMoney(metrics, 'gross_sales_pence')} icon={<TrendingUp size={16} />} />
            <Kpi label="Paid orders" value={metrics.totals.paid_orders} icon={<ReceiptText size={16} />} />
            <Kpi label="Pending value" value={formatMetricMoney(metrics, 'pending_value_pence')} icon={<ShoppingCart size={16} />} />
            <Kpi label="Items sold" value={metrics.totals.items_sold} icon={<Images size={16} />} />
            <Kpi label="Customers" value={metrics.totals.unique_customers} icon={<Users size={16} />} />
            <Kpi label="Repeat customers" value={metrics.totals.repeat_customers} icon={<Users size={16} />} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]">
            <Panel>
              <SectionTitle title="Orders and revenue" />
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendRows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke="rgba(148, 163, 184, 0.18)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: 'rgb(156, 163, 175)', fontSize: 12 }} />
                    <YAxis yAxisId="left" tick={{ fill: 'rgb(156, 163, 175)', fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fill: 'rgb(156, 163, 175)', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ background: 'rgb(17, 24, 39)', border: '1px solid rgb(55, 65, 81)', borderRadius: 8 }}
                      formatter={(value, name) => (name === 'revenue' ? [formatMoney(Number(value) * 100, currency), 'Revenue'] : [value, name])}
                    />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="orders" stroke="#38bdf8" strokeWidth={2} dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="paid" stroke="#22c55e" strokeWidth={2} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <Panel>
              <SectionTitle title="Operational alerts" action={<AlertTriangle size={16} className="text-content-muted" />} />
              {metrics.alerts.length === 0 ? (
                <p className="text-sm text-content-muted">No active alerts.</p>
              ) : (
                <div className="space-y-2">
                  {metrics.alerts.map((alert) => (
                    <div key={alert.type} className={`rounded border px-3 py-2 text-sm ${statusClass(alert.type)}`}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">{alert.type.replace(/_/g, ' ')}</span>
                        <span>{alert.count}</span>
                      </div>
                      <p className="mt-1 text-xs opacity-90">{alert.message}</p>
                      {alert.order_ids.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {alert.order_ids.slice(0, 5).map((orderId) => (
                            <Link key={orderId} to={`/admin/orders/${orderId}`} className="text-xs underline">
                              #{orderId}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Panel>
              <SectionTitle title="Order status" />
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={statusRows} dataKey="count" nameKey="label" innerRadius={48} outerRadius={82} paddingAngle={2}>
                      {statusRows.map((row, index) => (
                        <Cell key={row.key} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: 'rgb(17, 24, 39)', border: '1px solid rgb(55, 65, 81)', borderRadius: 8 }} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <Panel>
              <SectionTitle title="Delivery health" />
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={deliveryRows} layout="vertical" margin={{ left: 12, right: 12 }}>
                    <CartesianGrid stroke="rgba(148, 163, 184, 0.18)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'rgb(156, 163, 175)', fontSize: 12 }} allowDecimals={false} />
                    <YAxis dataKey="label" type="category" width={110} tick={{ fill: 'rgb(156, 163, 175)', fontSize: 12 }} />
                    <Tooltip contentStyle={{ background: 'rgb(17, 24, 39)', border: '1px solid rgb(55, 65, 81)', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <MoneyTable metrics={metrics} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Panel>
              <SectionTitle title="Top events" />
              <div className="space-y-3">
                {metrics.top_events.map((event) => (
                  <div key={`${event.event_id}-${event.event_slug}`} className="grid grid-cols-[1fr_auto] gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-content">{event.event_name}</p>
                      <p className="text-xs text-content-muted">{event.item_count} items</p>
                    </div>
                    <div className="text-right text-content">
                      <p>{event.paid_order_count}</p>
                      <p className="text-xs text-content-muted">orders</p>
                    </div>
                  </div>
                ))}
                {metrics.top_events.length === 0 && <p className="text-sm text-content-muted">No paid events.</p>}
              </div>
            </Panel>

            <Panel>
              <SectionTitle title="Top photos" />
              <div className="space-y-3">
                {metrics.top_photos.map((photo) => (
                  <div key={photo.photo_id} className="grid grid-cols-[1fr_auto] gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-content">{photo.photo_id}</p>
                      <p className="truncate text-xs text-content-muted">{photo.event_slug ?? 'Unknown event'}</p>
                    </div>
                    <div className="text-right text-content">
                      <p>{photo.item_count}</p>
                      <p className="text-xs text-content-muted">sold</p>
                    </div>
                  </div>
                ))}
                {metrics.top_photos.length === 0 && <p className="text-sm text-content-muted">No photo sales.</p>}
              </div>
            </Panel>

            <Panel>
              <SectionTitle title="Top customers" />
              <div className="space-y-3">
                {metrics.top_customers.map((customer) => (
                  <div key={customer.email} className="grid grid-cols-[1fr_auto] gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate text-content">{customer.email}</p>
                      <p className="text-xs text-content-muted">
                        {customer.last_order_at ? new Date(customer.last_order_at).toLocaleDateString() : 'No date'}
                      </p>
                    </div>
                    <div className="text-right text-content">
                      <p>{customer.paid_order_count}</p>
                      <p className="text-xs text-content-muted">orders</p>
                    </div>
                  </div>
                ))}
                {metrics.top_customers.length === 0 && <p className="text-sm text-content-muted">No paid customers.</p>}
              </div>
            </Panel>
          </div>

          <Panel>
            <SectionTitle title="Recent activity" />
            <div className="divide-y divide-surface-700">
              {metrics.recent_activity.map((entry) => (
                <div key={`${entry.source}-${entry.id}`} className="grid grid-cols-1 gap-2 py-3 text-sm md:grid-cols-[1fr_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded border px-2 py-0.5 text-xs ${statusClass(entry.status ?? entry.action)}`}>
                        {entry.source}
                      </span>
                      <span className="font-medium text-content">{entry.action.replace(/_/g, ' ')}</span>
                      {entry.order_id && (
                        <Link to={`/admin/orders/${entry.order_id}`} className="text-xs text-sky-400 hover:text-sky-300">
                          #{entry.order_id}
                        </Link>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs text-content-muted">{entry.message}</p>
                  </div>
                  <span className="text-xs text-content-muted md:text-right">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>
              ))}
              {metrics.recent_activity.length === 0 && <p className="py-3 text-sm text-content-muted">No recent activity.</p>}
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
