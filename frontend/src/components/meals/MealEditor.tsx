import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { mealsApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { MEAL_TYPES } from '@/lib/labels'
import { localInput, nowIn, num, todayIn } from '@/lib/format'
import { ConfidenceBadge, kcalRange, useConfirmMeal } from './MealBits'
import { ItemsEditor, emptyItem, itemDraft, toItems, type ItemDraft } from './ItemsEditor'
import { MealPhotos } from './MealPhotos'
import type { Meal, MealPatch, MealType } from '@/types'

interface Form {
  title: string
  meal_type: MealType | null
  eaten_at: string
  note: string
  items: ItemDraft[]
}

const comparable = (items: ItemDraft[]) =>
  JSON.stringify(items.map(({ key: _key, ...rest }) => rest))

/** Viewing and editing one meal, or writing a new one (no `meal`). */
export function MealEditor({
  meal,
  onDone,
  onCreated,
}: {
  meal?: Meal
  onDone: () => void
  onCreated?: (meal: Meal) => void
}) {
  const user = useUser()
  const client = useQueryClient()
  const initial = useMemo<Form>(
    () =>
      meal
        ? {
            title: meal.title,
            meal_type: meal.meal_type,
            eaten_at: localInput(meal.eaten_at),
            note: meal.note ?? '',
            items: meal.items.map(itemDraft),
          }
        : {
            title: '',
            meal_type: null,
            eaten_at: nowIn(user.timezone),
            note: '',
            items: [emptyItem()],
          },
    [meal, user.timezone],
  )
  const [form, setForm] = useState<Form>(initial)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const confirmMeal = useConfirmMeal()

  const itemsChanged = comparable(form.items) !== comparable(initial.items)
  const dirty =
    itemsChanged ||
    form.title !== initial.title ||
    form.meal_type !== initial.meal_type ||
    form.eaten_at !== initial.eaten_at ||
    form.note !== initial.note

  const save = useMutation({
    mutationFn: async () => {
      if (!form.title.trim()) throw new Error('Напишите название')
      if (!form.eaten_at) throw new Error('Укажите время')
      const items = toItems(form.items)
      if (typeof items === 'string') throw new Error(items)
      const note = form.note.trim() || null
      if (!meal)
        return mealsApi.create({
          title: form.title.trim(),
          meal_type: form.meal_type,
          eaten_at: form.eaten_at,
          note,
          items,
        })
      const patch: MealPatch = {}
      if (form.title !== initial.title) patch.title = form.title.trim()
      if (form.meal_type !== initial.meal_type) patch.meal_type = form.meal_type
      if (form.eaten_at !== initial.eaten_at) patch.eaten_at = form.eaten_at
      if (form.note !== initial.note) patch.note = note
      // Sending items marks the numbers as the person's own: only when they changed.
      if (itemsChanged) patch.items = items
      return mealsApi.update(meal.id, patch)
    },
    onMutate: () => setError(''),
    onSuccess: async (value) => {
      client.setQueryData(keys.meal(value.id), value)
      await invalidateMeals(client)
      if (meal) {
        toast.success('Изменения сохранены')
        onDone()
      } else {
        onCreated?.(value)
        onDone()
      }
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })

  const remove = useMutation({
    mutationFn: () => mealsApi.remove(meal!.id),
    onSuccess: async () => {
      client.removeQueries({ queryKey: keys.meal(meal!.id) })
      await invalidateMeals(client)
      toast.success('Запись удалена')
      onDone()
    },
    // Storage cleanup can fail after the record is gone: show the truth either way.
    onError: () => invalidateMeals(client),
    meta: { silent: true },
  })

  const set = <K extends keyof Form>(field: K, value: Form[K]) =>
    setForm((current) => ({ ...current, [field]: value }))

  const range = meal ? kcalRange(meal) : ''
  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      {meal?.status === 'draft' && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[14px] border border-dashed border-warning/60 bg-warning-soft px-4 py-3">
          <p className="text-sm">
            <span className="font-medium">Черновик.</span> Не учитывается в итогах дня.
            {dirty && (
              <span className="block text-muted-foreground">Сначала сохраните изменения.</span>
            )}
          </p>
          <Button
            type="button"
            size="sm"
            onClick={() => confirmMeal.mutate(meal.id)}
            disabled={confirmMeal.isPending || dirty}
          >
            <Check />
            Сохранить в дневник
          </Button>
        </div>
      )}

      {meal && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl font-semibold tracking-tight">{num(meal.kcal)} ккал</span>
            {range && <span className="text-sm text-muted-foreground">диапазон {range}</span>}
          </div>
          <ConfidenceBadge meal={meal} />
          {meal.estimated_by === 'ai' && meal.assumptions.length > 0 && (
            <div className="rounded-[14px] bg-muted px-4 py-3 text-sm">
              <p className="mb-1 font-medium">Допущения AI</p>
              <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                {meal.assumptions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          <MealPhotos meal={meal} />
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Label htmlFor="meal-title">Название</Label>
        <Input
          id="meal-title"
          value={form.title}
          onChange={(event) => set('title', event.target.value)}
          maxLength={200}
          placeholder="Например, обед в столовой"
          required
        />
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium" id="meal-type-label">
          Прием пищи
        </span>
        <ToggleGroup
          type="single"
          className="chips w-full"
          value={form.meal_type ?? ''}
          onValueChange={(value) => set('meal_type', (value || null) as MealType | null)}
          aria-labelledby="meal-type-label"
        >
          {MEAL_TYPES.map((type) => (
            <ToggleGroupItem key={type.value} value={type.value}>
              {type.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {!meal && !form.meal_type && (
          <p className="text-xs text-muted-foreground">Не выбрано — определится по времени.</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="meal-time">Когда</Label>
        <Input
          id="meal-time"
          type="datetime-local"
          value={form.eaten_at}
          max={`${todayIn(user.timezone)}T23:59`}
          onChange={(event) => set('eaten_at', event.target.value)}
          required
          className="w-full sm:w-64"
        />
      </div>

      <ItemsEditor items={form.items} onChange={(items) => set('items', items)} />

      <div className="flex flex-col gap-2">
        <Label htmlFor="meal-note">Заметка</Label>
        <Textarea
          id="meal-note"
          value={form.note}
          onChange={(event) => set('note', event.target.value)}
          maxLength={1000}
          rows={2}
        />
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        {meal ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => setDeleting(true)}
          >
            <Trash2 />
            Удалить запись
          </Button>
        ) : (
          <span />
        )}
        <Button
          type="submit"
          disabled={save.isPending || (!!meal && !dirty)}
          className="sm:min-w-44"
        >
          {save.isPending ? 'Сохраняем…' : meal ? 'Сохранить изменения' : 'Добавить'}
        </Button>
      </div>

      {meal && (
        <ConfirmDialog
          open={deleting}
          onOpenChange={setDeleting}
          title={`Удалить «${meal.title}»?`}
          description="Запись и ее фото удалятся без возможности восстановления."
          onConfirm={() => remove.mutateAsync()}
        />
      )}
    </form>
  )
}
