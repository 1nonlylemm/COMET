/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          bg: 'var(--color-brand-bg)',
          surface: 'var(--color-brand-surface)',
          'surface-solid': 'var(--color-brand-surface-solid)',
          border: 'var(--color-brand-border)',
          primary: 'var(--color-brand-primary)',
          'primary-light': 'var(--color-brand-primary-light)',
          accent: 'var(--color-brand-accent)',
          danger: 'var(--color-brand-danger)',
          success: 'var(--color-brand-success)',
          text: 'var(--color-brand-text)',
          'text-muted': 'var(--color-brand-text-muted)',
        },
        background: 'var(--color-background)',
      },
      fontFamily: {
        display: ['Outfit', 'Plus Jakarta Sans', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },
      backdropBlur: {
        md: '12px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
