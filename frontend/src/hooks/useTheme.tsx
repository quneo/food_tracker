import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
type Theme = 'light' | 'dark'

const KEY = 'food-theme'
const COLORS: Record<Theme, string> = { light: '#f8f7f2', dark: '#0d1210' }
const ThemeContext = createContext<{
  preference: ThemePreference
  resolvedTheme: Theme
  setTheme: (theme: ThemePreference) => void
}>(null!)

function readPreference(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches

function apply(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', COLORS[theme])
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(readPreference)
  const [system, setSystem] = useState<Theme>(() => (systemDark() ? 'dark' : 'light'))
  const resolvedTheme = preference === 'system' ? system : preference

  useEffect(() => apply(resolvedTheme), [resolvedTheme])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setSystem(media.matches ? 'dark' : 'light')
    media.addEventListener('change', update)
    const sync = (event: StorageEvent) => {
      if (event.key === KEY) setPreference(readPreference())
    }
    window.addEventListener('storage', sync)
    return () => {
      media.removeEventListener('change', update)
      window.removeEventListener('storage', sync)
    }
  }, [])

  function setTheme(value: ThemePreference) {
    try {
      if (value === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, value)
    } catch {
      /* Storage can be unavailable (private mode, Telegram webviews): keep it in memory. */
    }
    apply(value === 'system' ? (systemDark() ? 'dark' : 'light') : value)
    setPreference(value)
  }

  return (
    <ThemeContext.Provider value={{ preference, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
