import { cn } from '@/lib/utils'
import mark from '@/assets/app-mark.png'

/** The app's icon, the same picture as on the phone's home screen. */
export function AppMark({ className }: { className?: string }) {
  return (
    <img
      src={mark}
      alt=""
      aria-hidden="true"
      draggable={false}
      className={cn('size-8 shrink-0 select-none', className)}
    />
  )
}
