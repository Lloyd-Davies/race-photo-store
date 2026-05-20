import { apiGet, apiPatch, apiPost } from './client'

export interface EmailConfig {
  email_enabled: boolean
  provider: string
  from_address: string
  from_name: string
  brevo_key_set: boolean
  support_email: string
  order_email_required: boolean
}

export interface EmailTestResult {
  sent: boolean
  email_enabled: boolean
  provider: string
  from_address: string
  message: string
}

export interface CheckoutSettings {
  default_photo_price_pence: number
  currency: string
  allow_stripe_promotion_codes: boolean
}

export interface AdminSettings {
  checkout: CheckoutSettings
  stripe_secret_key_set: boolean
  stripe_webhook_secret_set: boolean
  public_base_url: string
  site_name: string
  site_tagline: string
  email: EmailConfig
}

export const fetchEmailConfig = () =>
  apiGet<EmailConfig>('/admin/email/config')

export const sendTestEmail = (to_email: string) =>
  apiPost<EmailTestResult>('/admin/email/test', { to_email })

export const fetchAdminSettings = () =>
  apiGet<AdminSettings>('/admin/settings')

export const updateCheckoutSettings = (body: Partial<CheckoutSettings>) =>
  apiPatch<AdminSettings>('/admin/settings/checkout', body)
