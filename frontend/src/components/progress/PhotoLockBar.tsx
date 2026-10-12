import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, LockOpen } from 'lucide-react'
import { photoLockApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { usePhotoLock } from '@/hooks/usePhotoLock'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { timeOfInstant } from '@/lib/format'

/** Above the photos: hidden behind the code, or open until a moment. */
export function PhotoLockBar() {
  const client = useQueryClient()
  const { lock, hidden } = usePhotoLock()
  const [asking, setAsking] = useState(false)
  const close = useMutation({
    mutationFn: () => photoLockApi.lock(),
    onSuccess: (state) => client.setQueryData(keys.photoLock, state),
  })

  if (!lock) return null
  if (!lock.enabled)
    return (
      <p className="text-sm text-muted-foreground">
        Фото видны всем, кто откроет дневник.{' '}
        <Link
          to="/profile?section=account"
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          Задать код
        </Link>
      </p>
    )
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[16px] glass px-4 py-3">
      <p className="flex items-center gap-2.5 text-sm">
        {hidden ? (
          <Lock className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : (
          <LockOpen className="size-4 shrink-0 text-primary" aria-hidden="true" />
        )}
        {hidden
          ? 'Фото скрыты кодом'
          : `Фото открыты до ${lock.unlocked_until ? timeOfInstant(lock.unlocked_until) : ''}`}
      </p>
      {hidden ? (
        <Button size="sm" onClick={() => setAsking(true)}>
          Показать
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => close.mutate()}
          disabled={close.isPending}
        >
          Скрыть
        </Button>
      )}
      <ResponsiveSheet open={asking} onOpenChange={setAsking} title="Код для фото">
        {asking && <UnlockForm onDone={() => setAsking(false)} />}
      </ResponsiveSheet>
    </div>
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
