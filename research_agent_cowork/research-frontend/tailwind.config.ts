import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Reforge-inspired dark theme
        sidebar: {
          bg: '#0A0A0A',
          hover: '#1A1A1A',
          border: '#1F1F1F',
        },
        main: {
          bg: '#000000',
          secondary: '#0A0A0A',
          input: '#111111',
        },
        accent: {
          primary: '#45BFFF',
          secondary: '#3AADEF',
          muted: '#2A6F9E',
        },
        brand: {
          blue: '#45BFFF',
          'blue-hover': '#6DD0FF',
          'blue-muted': '#2A6F9E',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        serif: ['Instrument Serif', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Menlo', 'Monaco', 'monospace'],
        display: ['Instrument Serif', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
export default config
