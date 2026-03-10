import { apiGet, apiPost } from './client'

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

export const fetchEmailConfig = () =>
  apiGet<EmailConfig>('/admin/email/config')

export const sendTestEmail = (to_email: string) =>
  apiPost<EmailTestResult>('/admin/email/test', { to_email })
