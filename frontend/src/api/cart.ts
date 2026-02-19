import { apiPost } from './client'

export interface CartResponse {
  cart_id: string
  count: number
}

export interface CheckoutResponse {
  order_id: number
  stripe_checkout_url: string
}

export const createCart = (body: {
  event_id: number
  photo_ids: string[]
  email?: string
}) => apiPost<CartResponse>('/carts', body)

export const createCheckout = (cart_id: string) =>
  apiPost<CheckoutResponse>('/checkout', { cart_id })
