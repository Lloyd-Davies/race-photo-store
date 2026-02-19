import { type ButtonHTMLAttributes } from 'react'
import { clsx } from '../utils/clsx'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const variants: Record<Variant, string> = {
  primary:
    'bg-sky-500 hover:bg-sky-600 active:bg-sky-700 text-white shadow-sm',
  secondary:
    'bg-surface-800 hover:bg-surface-700 border border-surface-600 text-content',
  ghost:
    'bg-transparent hover:bg-surface-800 text-content-muted hover:text-content',
  danger:
    'bg-red-600 hover:bg-red-700 text-white',
}

const sizes: Record<Size, string> = {
  sm: 'text-xs px-3 py-1.5 rounded',
  md: 'text-sm px-4 py-2 rounded-md',
  lg: 'text-base px-6 py-2.5 rounded-md',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={clsx(
        'font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 disabled:opacity-50 disabled:pointer-events-none',
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {children}
        </span>
      ) : (
        children
      )}
    </button>
  )
}
