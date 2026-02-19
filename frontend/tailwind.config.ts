import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Surface scale — adapt via CSS custom properties
        surface: {
          950: 'rgb(var(--s-950) / <alpha-value>)',
          900: 'rgb(var(--s-900) / <alpha-value>)',
          800: 'rgb(var(--s-800) / <alpha-value>)',
          700: 'rgb(var(--s-700) / <alpha-value>)',
          600: 'rgb(var(--s-600) / <alpha-value>)',
        },
        // Adaptive text — primary and muted
        content: {
          DEFAULT: 'rgb(var(--c-text) / <alpha-value>)',
          muted:   'rgb(var(--c-muted) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
