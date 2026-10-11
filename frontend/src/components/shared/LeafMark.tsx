import { cn } from '@/lib/utils'

/** The app's mark: a leaf on a green tile, the stem in the calorie color. */
export function LeafMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-8', className)}>
      <rect width="32" height="32" rx="9" fill="var(--primary)" />
      <path
        d="M9.5 21.5c0-6.6 4.6-11 13-11.5-.4 8.3-4.8 13-11.4 13-.6 0-1.1 0-1.6-.1"
        fill="none"
        stroke="var(--primary-foreground)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 24c3.2-3.6 6.3-6.2 10-8.3"
        fill="none"
        stroke="var(--kcal)"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  )
}
