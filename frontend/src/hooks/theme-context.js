import { createContext } from 'react'

export const ThemeContext = createContext({
  theme: 'system',
  mode: 'light',
  setTheme: () => null,
})
