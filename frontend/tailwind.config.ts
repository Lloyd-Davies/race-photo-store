import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Surface scale: dark editorial palette
        surface: {
          950: '#030712', // near-black page bg
          900: '#111827', // card bg
          800: '#1f2937', // raised surface
          700: '#374151', // border
          600: '#4b5563', // muted border
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
