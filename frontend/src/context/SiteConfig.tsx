import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchSiteConfig, type SiteConfig } from '../api/siteConfig'

const DEFAULT: SiteConfig = {
  site_name: 'Race Photos',
  site_tagline: 'Your race, your photos.',
  allow_stripe_promotion_codes: false,
  seo_site_url: window.location.origin,
  seo_default_title: 'Race Photos | Race and Event Photos',
  seo_title_template: '{page} | {site_name}',
  seo_default_description: 'Browse and purchase photographs from running, athletics and sporting events.',
  seo_logo_url: `${window.location.origin}/favicon.svg`,
}

const SiteConfigContext = createContext<SiteConfig>(DEFAULT)

export function SiteConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<SiteConfig>(DEFAULT)

  useEffect(() => {
    fetchSiteConfig()
      .then((settings) => setConfig({ ...DEFAULT, ...settings }))
      .catch(() => { /* keep defaults if API unreachable */ })
  }, [])

  return (
    <SiteConfigContext.Provider value={config}>
      {children}
    </SiteConfigContext.Provider>
  )
}

export const useSiteConfig = () => useContext(SiteConfigContext)
