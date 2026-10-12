import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, LockOpen } from 'lucide-react'
import { toast } from 'sonner'
import { photoLockApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { usePhotoLock } from '@/hooks/usePhotoLock'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { timeOfInstant } from '@/lib/format'

/** In the page header: a closed lock shows the photos (after the code), an open one hides
 * them again. Nothing when no code is set. */
export function PhotoLockButton() {
  const client = useQueryClient()
  const { lock, hidden } = usePhotoLock()
  const [asking, setAsking] = useState(false)
  const close = useMutation({
    mutationFn: () => photoLockApi.lock(),
    onSuccess: (state) => {
      client.setQueryData(keys.photoLock, state)
      toast.success('Фото скрыты')
    },
  })
  if (!lock?.enabled) return null
  return (
    <>
      {hidden ? (
        <Button
          variant="outline"
          size="icon"
          onClick={() => setAsking(true)}
          aria-label="Показать фото"
          title="Показать фото"
        >
          <Lock />
        </Button>
      ) : (
        <Button
          variant="outline"
          size="icon"
          onClick={() => close.mutate()}
          disabled={close.isPending}
          aria-label={`Скрыть фото (открыты до ${lock.unlocked_until ? timeOfInstant(lock.unlocked_until) : ''})`}
          title="Скрыть фото"
          className="text-primary"
        >
          <LockOpen />
        </Button>
      )}
      <PinSheet open={asking} onOpenChange={setAsking} />
    </>
  )
}

/** Asks for the photo code; `onUnlocked` runs after it opens the photos. */
export function PinSheet({
  open,
  onOpenChange,
  onUnlocked,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUnlocked?: () => void
}) {
  return (
    <ResponsiveSheet open={open} onOpenChange={onOpenChange} title="Код для фото">
      {open && (
        <UnlockForm
          onDone={() => {
            onOpenChange(false)
            onUnlocked?.()
          }}
        />
      )}
    </ResponsiveSheet>
  )
}

function UnlockForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const unlock = useMutation({
    mutationFn: () => photoLockApi.unlock(pin),
    onMutate: () => setError(''),
    onSuccess: (state) => {
      client.setQueryData(keys.photoLock, state)
      toast.success(
        state.unlocked_until
          ? `Фото открыты до ${timeOfInstant(state.unlocked_until)}`
          : 'Фото открыты',
      )
      onDone()
    },
    onError: (e) => {
      setError(e.message)
      setPin('')
    },
    meta: { silent: true },
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (pin.length >= 4) unlock.mutate()
      }}
    >
      <Input
        value={pin}
        onChange={(event) => setPin(event.target.value.replace(/\D/g, '').slice(0, 8))}
        inputMode="numeric"
        autoComplete="off"
        autoFocus
        type="password"
        aria-label="Код"
        placeholder="••••"
        className="h-14 text-center text-2xl tracking-[0.5em]"
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pin.length < 4 || unlock.isPending}>
        {unlock.isPending ? 'Проверяем…' : 'Показать фото'}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        Фото откроются на 15 минут в этом браузере.
      </p>
    </form>
  )
}

/** Under the album while no code is set. */
export function LockHint() {
  const { lock } = usePhotoLock()
  if (!lock || lock.enabled) return null
  return (
    <p className="px-1 text-sm text-muted-foreground">
      Фото видны всем, кто откроет дневник.{' '}
      <Link
        to="/profile?section=account"
        className="font-medium text-primary underline-offset-4 hover:underline"
      >
        Задать код
      </Link>
    </p>
  )
}
