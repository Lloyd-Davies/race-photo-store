import { apiGet } from './client'

export interface SiteConfig {
  site_name: string
  site_tagline: string
  allow_stripe_promotion_codes: boolean
}

export const fetchSiteConfig = () => apiGet<SiteConfig>('/config')
