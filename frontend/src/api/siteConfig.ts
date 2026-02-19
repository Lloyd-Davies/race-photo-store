import { apiGet } from './client'

export interface SiteConfig {
  site_name: string
  site_tagline: string
}

export const fetchSiteConfig = () => apiGet<SiteConfig>('/config')
