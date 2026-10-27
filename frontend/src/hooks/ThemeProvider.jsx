import { useEffect, useState } from 'react'
import { ThemeContext } from './theme-context'

function getStoredTheme() {
  if (typeof window === 'undefined') {
    return 'system'
  }

  const saved = window.localStorage.getItem('brand-theme')
  return saved || 'system'
}

function getSystemMode() {
  if (typeof window === 'undefined') {
    return 'light'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getStoredTheme)
  const [systemMode, setSystemMode] = useState(getSystemMode)
  const mode = theme === 'system' ? systemMode : theme

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(mode)
    root.style.colorScheme = mode
    window.localStorage.setItem('brand-theme', theme)
  }, [mode, theme])

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event) => {
      setSystemMode(event.matches ? 'dark' : 'light')
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, mode, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export default ThemeProvider
