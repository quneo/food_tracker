import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useUser } from '@/hooks/useAuth'

export function PageHeader({
  title,
  meta,
  children,
}: {
  title: ReactNode
  meta?: ReactNode
  children?: ReactNode
}) {
  const { pathname } = useLocation()
  return (
    <div className="page-heading">
      <div className="min-w-0">
        <h1>{title}</h1>
        {meta && <p className="page-meta">{meta}</p>}
      </div>
      <div className="page-actions">
        {children}
        {pathname !== '/profile' && <ProfileAvatar />}
      </div>
    </div>
  )
}

/** On a phone the tab bar has no room for the profile: it opens from here. */
function ProfileAvatar() {
  const user = useUser()
  return (
    <Link to="/profile" className="header-avatar" aria-label="Профиль">
      {(user.name.trim()[0] ?? '?').toUpperCase()}
    </Link>
  )
}
