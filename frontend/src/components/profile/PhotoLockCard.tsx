import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { photoLockApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { usePhotoLock } from '@/hooks/usePhotoLock'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { PhotoLock } from '@/types'

type Mode = 'idle' | 'set' | 'change' | 'remove'
const digits = (text: string) => text.replace(/\D/g, '').slice(0, 8)

/** The code that hides progress photos: set it, change it, turn it off, reset via Telegram. */
export function PhotoLockCard() {
  const user = useUser()
  const client = useQueryClient()
  const { lock } = usePhotoLock()
  const [mode, setMode] = useState<Mode>('idle')
  const [current, setCurrent] = useState('')
  const [pin, setPin] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')

  function open(next: Mode) {
    setMode(next)
    setCurrent('')
    setPin('')
    setRepeat('')
    setError('')
  }
  const saved = (state: PhotoLock, message: string) => {
    client.setQueryData(keys.photoLock, state)
    toast.success(message)
    open('idle')
  }
  const save = useMutation({
    mutationFn: async () => {
      if (mode === 'remove') return photoLockApi.remove(current)
      if (pin.length < 4) throw new Error('Код — от 4 до 8 цифр')
      if (pin !== repeat) throw new Error('Коды не совпадают')
      return photoLockApi.set(pin, mode === 'change' ? current : undefined)
    },
    onMutate: () => setError(''),
    onSuccess: (state) =>
      saved(
        state,
        mode === 'remove' ? 'Код отключен' : mode === 'change' ? 'Код изменен' : 'Код включен',
      ),
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })
  const reset = useMutation({
    mutationFn: () => photoLockApi.reset(),
    onSuccess: () => toast.success('Подтвердите сброс в чате с ботом'),
  })

  if (!lock) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>Код для фото прогресса</CardTitle>
        <CardDescription>
          {lock.enabled
            ? 'Фото прогресса показываются размытыми, пока в браузере не введен код.'
            : 'Задайте код, и фото прогресса будут размыты, пока его не введут.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {mode === 'idle' ? (
          <div className="flex flex-wrap gap-2">
            {lock.enabled ? (
              <>
                <Button variant="outline" onClick={() => open('change')}>
                  Сменить код
                </Button>
                <Button variant="ghost" onClick={() => open('remove')}>
                  Отключить
                </Button>
                {user.telegram_id && (
                  <Button
                    variant="ghost"
                    className="text-muted-foreground"
                    onClick={() => reset.mutate()}
                    disabled={reset.isPending}
                  >
                    Забыли код?
                  </Button>
                )}
              </>
            ) : (
              <Button onClick={() => open('set')}>Задать код</Button>
            )}
          </div>
        ) : (
          <form
            className="flex max-w-sm flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              save.mutate()
            }}
          >
            {(mode === 'change' || mode === 'remove') && (
              <PinField
                id="pin-current"
                label="Текущий код"
                value={current}
                onChange={setCurrent}
              />
            )}
            {mode !== 'remove' && (
              <>
                <PinField id="pin-new" label="Новый код, 4–8 цифр" value={pin} onChange={setPin} />
                <PinField id="pin-repeat" label="Еще раз" value={repeat} onChange={setRepeat} />
              </>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={save.isPending}>
                {mode === 'remove' ? 'Отключить код' : 'Сохранить'}
              </Button>
              <Button type="button" variant="ghost" onClick={() => open('idle')}>
                Отмена
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

function PinField({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="password"
        inputMode="numeric"
        autoComplete="off"
        value={value}
        onChange={(event) => onChange(digits(event.target.value))}
        className="tracking-[0.3em]"
      />
    </div>
  )
}
