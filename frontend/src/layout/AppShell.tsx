import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { ChartColumnBig, House, NotebookText, PersonStanding, UserRound } from 'lucide-react'
import { PageReveal } from '@/components/shared/PageReveal'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { LeafMark } from '@/components/shared/LeafMark'
import { MealSheetHost } from '@/components/meals/MealSheet'

const LINKS = [
  { to: '/', label: 'Главная', title: 'Сегодня', icon: House },
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
          <ThemeToggle />
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
