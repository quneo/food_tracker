import type { ReactNode } from 'react'
import { RefreshCw, type LucideIcon } from 'lucide-react'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { LeafMark } from './LeafMark'

export function SplashScreen() {
  return (
    <main className="splash" aria-busy="true" aria-label="Загрузка">
      <LeafMark className="size-12 animate-pulse" />
    </main>
  )
}

export function PageSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Загрузка">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-40 w-full rounded-[20px]" />
      <Skeleton className="h-64 w-full rounded-[20px]" />
    </div>
  )
}

export function BlockSkeleton({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-3', className)} aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-14 w-full rounded-[14px]" />
      ))}
    </div>
  )
}

export function ErrorState({
  error,
  retry,
  className,
}: {
  error: Error
  retry?: () => void
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-start gap-3 rounded-[20px] border border-destructive/30 bg-card p-5',
        className,
      )}
    >
      <div>
        <p className="font-medium">Не удалось загрузить</p>
        <p className="muted text-sm">{error.message}</p>
      </div>
      {retry && (
        <Button variant="outline" onClick={retry}>
          <RefreshCw />
          Повторить
        </Button>
      )}
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  className,
}: {
  icon: LucideIcon
  title: string
  description?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <Empty className={cn('gap-4 p-6 md:p-8', className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="size-12 rounded-2xl bg-accent text-accent-foreground">
          <Icon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description && <EmptyDescription>{description}</EmptyDescription>}
      </EmptyHeader>
      {children && (
        <EmptyContent className="flex-row flex-wrap justify-center">{children}</EmptyContent>
      )}
    </Empty>
  )
}
