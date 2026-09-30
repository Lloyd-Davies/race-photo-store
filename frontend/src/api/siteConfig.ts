import { apiGet } from './client'

export interface SiteConfig {
  site_name: string
  site_tagline: string
  allow_stripe_promotion_codes: boolean
  seo_site_url: string
  seo_default_title: string
  seo_title_template: string
  seo_default_description: string
  seo_logo_url: string
}

export const fetchSiteConfig = () => apiGet<SiteConfig>('/config')
