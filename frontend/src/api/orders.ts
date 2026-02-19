import { apiGet } from './client'

export type OrderStatus = 'PENDING' | 'PAID' | 'BUILDING' | 'READY' | 'FAILED' | 'EXPIRED'

export interface Order {
  id: number
  status: OrderStatus
  download_url?: string
}

export const fetchOrder = (orderId: number) => apiGet<Order>(`/orders/${orderId}`)
