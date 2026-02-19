import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchSiteConfig, type SiteConfig } from '../api/siteConfig'

const DEFAULT: SiteConfig = {
  site_name: 'Race Photos',
  site_tagline: 'Your race, your photos.',
}

const SiteConfigContext = createContext<SiteConfig>(DEFAULT)

export function SiteConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<SiteConfig>(DEFAULT)

  useEffect(() => {
    fetchSiteConfig()
      .then(setConfig)
      .catch(() => { /* keep defaults if API unreachable */ })
  }, [])

  // Update document title whenever site name changes
  useEffect(() => {
    document.title = config.site_name
  }, [config.site_name])

  return (
    <SiteConfigContext.Provider value={config}>
      {children}
    </SiteConfigContext.Provider>
  )
}

export const useSiteConfig = () => useContext(SiteConfigContext)
