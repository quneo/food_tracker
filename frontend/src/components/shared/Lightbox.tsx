import { useEffect } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { Photo } from './Photo'

/** Full-size photos over the page; arrow keys and buttons move between them. */
export function Lightbox({
  ids,
  index,
  onIndexChange,
  onClose,
  title = 'Фото',
  version,
}: {
  ids: number[]
  index: number | null
  onIndexChange: (index: number) => void
  onClose: () => void
  title?: string
  version?: string
}) {
  const open = index !== null && ids.length > 0
  const current = index ?? 0
  useEffect(() => {
    if (!open) return
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight' && current < ids.length - 1) onIndexChange(current + 1)
      if (event.key === 'ArrowLeft' && current > 0) onIndexChange(current - 1)
    }
    window.addEventListener('keydown', keys)
    return () => window.removeEventListener('keydown', keys)
  }, [open, current, ids.length, onIndexChange])
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/90 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-50 flex items-center justify-center p-4 outline-none"
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">
            {title}
            {ids.length > 1 ? `, ${current + 1} из ${ids.length}` : ''}
          </DialogPrimitive.Title>
          {open && (
            <Photo
              key={ids[current]}
              id={ids[current]}
              alt={title}
              size="original"
              version={version}
              fit="contain"
              eager
              className="size-full bg-transparent text-white/70"
            />
          )}
          <DialogPrimitive.Close
            className="absolute top-[max(12px,env(safe-area-inset-top))] right-3 grid size-11 place-items-center rounded-full bg-black/50 text-white"
            aria-label="Закрыть"
          >
            <X className="size-5" />
          </DialogPrimitive.Close>
          {ids.length > 1 && (
            <>
              <button
                type="button"
                className="absolute left-3 grid size-11 place-items-center rounded-full bg-black/50 text-white disabled:opacity-30"
                onClick={() => onIndexChange(current - 1)}
                disabled={current === 0}
                aria-label="Предыдущее фото"
              >
                <ChevronLeft className="size-5" />
              </button>
              <button
                type="button"
                className="absolute right-3 grid size-11 place-items-center rounded-full bg-black/50 text-white disabled:opacity-30"
                onClick={() => onIndexChange(current + 1)}
                disabled={current === ids.length - 1}
                aria-label="Следующее фото"
              >
                <ChevronRight className="size-5" />
              </button>
              <span className="absolute bottom-[max(16px,env(safe-area-inset-bottom))] rounded-full bg-black/50 px-3 py-1 text-sm text-white">
                {current + 1} / {ids.length}
              </span>
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
