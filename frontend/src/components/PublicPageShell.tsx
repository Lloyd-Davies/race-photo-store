import { type ReactNode } from 'react'
import { clsx } from '../utils/clsx'

interface PublicPageShellProps {
  children: ReactNode
  className?: string
}

export default function PublicPageShell({ children, className }: PublicPageShellProps) {
  return (
    <div className={clsx('mx-auto w-full max-w-7xl min-w-0 px-4 py-8 sm:px-6 lg:py-12', className)}>
      {children}
    </div>
  )
}
