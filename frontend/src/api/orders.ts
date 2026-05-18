import { apiGet } from './client'

export type OrderStatus = 'PENDING' | 'PAID' | 'BUILDING' | 'READY' | 'FAILED' | 'EXPIRED'

export interface OrderDownloadItem {
  photo_id: string
  proof_url?: string
  download_url: string
}

export interface Order {
  id: number
  status: OrderStatus
  download_url?: string
  download_items: OrderDownloadItem[]
}

export const fetchOrder = (orderId: number, accessToken?: string) =>
  apiGet<Order>(
    `/orders/${orderId}`,
    accessToken ? { 'X-Order-Access': accessToken } : undefined,
  )
