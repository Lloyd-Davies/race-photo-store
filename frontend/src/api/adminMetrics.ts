import { apiGet } from './client'

export interface AdminMoneyMetric {
  currency: string
  gross_sales_pence: number
  paid_revenue_pence: number
  pending_value_pence: number
  discount_pence: number
  refunded_pence: number
  net_revenue_pence: number
  paid_order_count: number
  free_order_count: number
  average_order_value_pence: number
}

export interface AdminBreakdownMetric {
  key: string
  label: string
  count: number
  subtotal_pence: number
}

export interface AdminTrendPoint {
  date: string
  order_count: number
  paid_order_count: number
  item_count: number
  revenue_by_currency: Record<string, number>
  refunded_by_currency: Record<string, number>
  net_revenue_by_currency: Record<string, number>
}

export interface AdminPromotionCodeMetric {
  promotion_code: string
  promotion_code_id?: string
  order_count: number
  unique_customers: number
  money: AdminMoneyMetric[]
}

export interface AdminPricingCoverage {
  paid_orders: number
  authoritative_orders: number
  unsynced_orders: number
  failed_orders: number
}

export interface AdminEventMetric {
  event_id?: number
  event_slug: string
  event_name: string
  order_count: number
  paid_order_count: number
  item_count: number
  gross_sales: AdminMoneyMetric[]
}

export interface AdminPhotoMetric {
  photo_id: string
  event_slug?: string
  event_name?: string
  item_count: number
  order_count: number
  gross_sales: AdminMoneyMetric[]
}

export interface AdminCustomerMetric {
  email: string
  order_count: number
  paid_order_count: number
  last_order_at?: string
  gross_sales: AdminMoneyMetric[]
}

export interface AdminOperationalAlert {
  type: string
  severity: 'info' | 'warning' | 'critical' | string
  count: number
  message: string
  order_ids: number[]
}

export interface AdminActivity {
  id: number
  source: 'activity' | 'communication' | 'stripe'
  action: string
  actor?: string
  message: string
  status?: string
  order_id?: number
  created_at: string
  metadata: Record<string, unknown>
}

export interface AdminMetricsTotals {
  total_orders: number
  paid_orders: number
  pending_orders: number
  failed_orders: number
  ready_orders: number
  free_orders: number
  items_sold: number
  unique_customers: number
  repeat_customers: number
  average_items_per_order: number
  discounted_orders: number
  refunded_orders: number
}

export interface AdminStripeWebhookHealth {
  secret_configured: boolean
  last_valid_event_at?: string
  last_event_type?: string
  valid_events_24h: number
  processed_events_24h: number
  ignored_events_24h: number
}

export interface AdminMetrics {
  range: string
  generated_at: string
  start_at?: string
  end_at: string
  event_id?: number
  mixed_currency: boolean
  totals: AdminMetricsTotals
  money: AdminMoneyMetric[]
  status_breakdown: AdminBreakdownMetric[]
  delivery_health: AdminBreakdownMetric[]
  email_health: AdminBreakdownMetric[]
  top_events: AdminEventMetric[]
  top_photos: AdminPhotoMetric[]
  top_customers: AdminCustomerMetric[]
  daily_trends: AdminTrendPoint[]
  alerts: AdminOperationalAlert[]
  recent_activity: AdminActivity[]
  stripe_webhook_health: AdminStripeWebhookHealth
  pricing_coverage: AdminPricingCoverage
  promotion_codes: AdminPromotionCodeMetric[]
}

export type AdminMetricsRange = '7d' | '30d' | '90d' | '365d' | 'all'

export const fetchAdminMetrics = (params: { range: AdminMetricsRange; event_id?: number | 'ALL' }) => {
  const query = new URLSearchParams({ range: params.range })
  if (params.event_id && params.event_id !== 'ALL') query.set('event_id', String(params.event_id))
  return apiGet<AdminMetrics>(`/admin/metrics?${query}`)
}
