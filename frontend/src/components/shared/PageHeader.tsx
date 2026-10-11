import type { ReactNode } from 'react'

export function PageHeader({
  title,
  meta,
  children,
}: {
  title: string
  meta?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div className="min-w-0">
        <h1>{title}</h1>
        {meta && <p className="page-meta">{meta}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  )
}
