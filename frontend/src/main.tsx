import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { SiteConfigProvider } from './context/SiteConfig'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

const root = document.getElementById('root')!

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SiteConfigProvider>
          <App />
        </SiteConfigProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
