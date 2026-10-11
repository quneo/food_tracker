import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { ChartColumnBig, House, NotebookText, PersonStanding, UserRound } from 'lucide-react'
import { useUser } from '@/hooks/useAuth'
import { PageReveal } from '@/components/shared/PageReveal'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { LeafMark } from '@/components/shared/LeafMark'
import { MealSheetHost } from '@/components/meals/MealSheet'

const LINKS = [
  { to: '/', label: 'Сегодня', title: 'Сегодня', icon: House },
  { to: '/diary', label: 'Дневник', title: 'Дневник', icon: NotebookText },
  { to: '/analytics', label: 'Аналитика', title: 'Аналитика', icon: ChartColumnBig },
  { to: '/progress', label: 'Прогресс', title: 'Прогресс', icon: PersonStanding },
  { to: '/profile', label: 'Профиль', title: 'Профиль', icon: UserRound },
]

export function AppShell() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
    const page = LINKS.find((link) => link.to === pathname)
    document.title = page && page.title !== 'Дневник' ? `${page.title} — Дневник` : 'Дневник'
  }, [pathname])
  return (
    <div className="app-shell">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-xl focus:bg-card focus:px-4 focus:py-3"
      >
        К содержимому
      </a>
      <aside className="app-rail">
        <div className="rail-panel glass">
          <div className="app-brand">
            <LeafMark />
            Дневник
          </div>
          <nav className="app-nav" aria-label="Разделы">
            {LINKS.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end>
                <Icon aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="rail-footer">
            <RailUser />
            <ThemeToggle />
          </div>
        </div>
      </aside>
      <main id="main" className="main-content">
        <PageReveal key={pathname}>
          <Outlet />
        </PageReveal>
      </main>
      <MealSheetHost />
    </div>
  )
}

function RailUser() {
  const user = useUser()
  const initial = (user.name.trim()[0] ?? '?').toUpperCase()
  return (
    <Link to="/profile?section=account" className="rail-user">
      <span className="avatar-dot" aria-hidden="true">
        {initial}
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block truncate text-sm font-medium">{user.name}</span>
        <span className="block truncate text-xs text-muted-foreground">
          {user.telegram_id
            ? user.username
              ? `@${user.username}`
              : 'Telegram привязан'
            : 'Telegram не привязан'}
        </span>
      </span>
    </Link>
  )
}
