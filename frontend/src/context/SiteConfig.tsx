import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchSiteConfig, type SiteConfig } from '../api/siteConfig'

const DEFAULT: SiteConfig = {
  site_name: 'Race Photos',
  site_tagline: '',
  allow_stripe_promotion_codes: false,
  seo_site_url: 'https://photos.example.com',
  seo_default_title: 'Race Photos | Race and Event Photos',
  seo_title_template: '{page} | {site_name}',
  seo_default_description: 'Browse and purchase professional photographs from running, athletics and sporting events photographed by Race Photos.',
  seo_logo_url: 'https://photos.example.com/favicon.svg',
}

const SiteConfigContext = createContext<SiteConfig>(DEFAULT)

export function SiteConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<SiteConfig>(DEFAULT)

  useEffect(() => {
    fetchSiteConfig()
      .then(setConfig)
      .catch(() => { /* keep defaults if API unreachable */ })
  }, [])

  return (
    <SiteConfigContext.Provider value={config}>
      {children}
    </SiteConfigContext.Provider>
  )
}

export const useSiteConfig = () => useContext(SiteConfigContext)
