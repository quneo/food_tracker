import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/api/endpoints'
import { takeLaunch } from '@/lib/telegram'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  loading: boolean
  /** Why the Mini App sign-in failed (closed registration, blocked account…). */
  launchError: string
  signedIn: (user: User) => void
  refresh: () => Promise<void>
  logout: (everywhere?: boolean) => Promise<void>
  forget: () => void
}

const AuthContext = createContext<AuthState>(null!)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [launchError, setLaunchError] = useState('')
  const client = useQueryClient()

  useEffect(() => {
    let active = true
    async function boot() {
      const launch = takeLaunch()
      let current = await authApi.me().catch(() => null)
      // Opened from Telegram: sign in as the person Telegram vouches for, unless the
      // browser already holds that person's session.
      if (launch.initData && (!current || current.telegram_id !== launch.telegramId)) {
        try {
          current = await authApi.webapp(launch.initData, launch.invite)
        } catch (error) {
          if (active) setLaunchError((error as Error).message)
        }
      }
      if (active) {
        setUser(current)
        setLoading(false)
      }
    }
    boot()
    const expire = () => {
      setUser(null)
      client.clear()
    }
    window.addEventListener('session-expired', expire)
    return () => {
      active = false
      window.removeEventListener('session-expired', expire)
    }
  }, [client])

  const signedIn = useCallback(
    (value: User) => {
      client.clear()
      setLaunchError('')
      setUser(value)
    },
    [client],
  )

  const refresh = useCallback(async () => {
    setUser(await authApi.me())
  }, [])

  const forget = useCallback(() => {
    setUser(null)
    client.clear()
  }, [client])

  const logout = useCallback(
    async (everywhere = false) => {
      await (everywhere ? authApi.logoutAll() : authApi.logout())
      forget()
    },
    [forget],
  )

  return (
    <AuthContext.Provider value={{ user, loading, launchError, signedIn, refresh, logout, forget }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

/** The signed-in person; only for screens behind the sign-in gate. */
export function useUser() {
  const { user } = useAuth()
  if (!user) throw new Error('useUser outside the signed-in app')
  return user
}
