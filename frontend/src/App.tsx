import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { AppShell } from '@/layout/AppShell'
import { PageSkeleton, SplashScreen } from '@/components/shared/States'
import LoginPage from '@/pages/LoginPage'
import HomePage from '@/pages/HomePage'
import DiaryPage from '@/pages/DiaryPage'

const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const ProgressPage = lazy(() => import('@/pages/ProgressPage'))
const ProfilePage = lazy(() => import('@/pages/ProfilePage'))

function deferred(Page: ComponentType) {
  return function Deferred() {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Page />
      </Suspense>
    )
  }
}

// Signed-out visitors see the sign-in screen at the address they opened, so links from
// the bot (/diary?meal=12) still lead to the right place after signing in.
function Gate() {
  const { user, loading } = useAuth()
  if (loading) return <SplashScreen />
  return user ? <AppShell /> : <LoginPage />
}

export const router = createBrowserRouter([
  {
    Component: Gate,
    children: [
      { path: '/', Component: HomePage },
      { path: '/diary', Component: DiaryPage },
      { path: '/analytics', Component: deferred(AnalyticsPage) },
      { path: '/progress', Component: deferred(ProgressPage) },
      { path: '/profile', Component: deferred(ProfilePage) },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
