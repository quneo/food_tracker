import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { bodyApi } from '@/api/endpoints'
import { invalidateBody } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { addDays, inputNumber, localInput, nowIn, parseNumber, todayIn } from '@/lib/format'
import type { Weight } from '@/types'

/** Adds a weighing, or edits one when `entry` is given. */
export function WeightSheet({
  open,
  onOpenChange,
  entry,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  entry?: Weight | null
}) {
  return (
    <ResponsiveSheet
      open={open}
      onOpenChange={onOpenChange}
      title={entry ? 'Взвешивание' : 'Новое взвешивание'}
    >
      {open && <WeightForm entry={entry ?? null} onDone={() => onOpenChange(false)} />}
    </ResponsiveSheet>
  )
}

function WeightForm({ entry, onDone }: { entry: Weight | null; onDone: () => void }) {
  const user = useUser()
  const client = useQueryClient()
  const [weight, setWeight] = useState(inputNumber(entry?.weight_kg))
  const [when, setWhen] = useState(entry ? localInput(entry.measured_at) : nowIn(user.timezone))
  const [note, setNote] = useState(entry?.note ?? '')
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => {
      const value = parseNumber(weight)
      if (value === null || value < 20 || value > 400) throw new Error('Вес от 20 до 400 кг')
      const data = { weight_kg: value, measured_at: when || null, note: note.trim() || null }
      return entry ? bodyApi.updateWeight(entry.id, data) : bodyApi.addWeight(data)
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success(entry ? 'Сохранено' : 'Вес записан')
      onDone()
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="weight-value">Вес, кг</Label>
        <Input
          id="weight-value"
          value={weight}
          onChange={(event) => setWeight(event.target.value)}
          inputMode="decimal"
          autoComplete="off"
          placeholder="Например, 72,4"
          autoFocus
          required
          className="text-lg"
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="weight-time">Когда</Label>
        <Input
          id="weight-time"
          type="datetime-local"
          value={when}
          max={`${todayIn(user.timezone)}T23:59`}
          onChange={(event) => setWhen(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="weight-note">Заметка</Label>
        <Input
          id="weight-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Сохраняем…' : 'Сохранить'}
      </Button>
    </form>
  )
}

/** Change of the latest weight against the last one at least `days` earlier (newest first). */
export function weightChange(weights: Weight[], days = 7) {
  const latest = weights[0]
  if (!latest) return null
  const limit = addDays(latest.measured_on, -days)
  const before = weights.find((entry) => entry.measured_on <= limit)
  return before ? Number((latest.weight_kg - before.weight_kg).toFixed(1)) : null
}
