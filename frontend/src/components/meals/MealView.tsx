import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, PencilLine, Tag, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { mealsApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { MACROS, mealTypeLabel } from '@/lib/labels'
import { dayLabel, itemWeight, num, timeOf, todayIn } from '@/lib/format'
import { ConfidenceBadge, MacroLine, kcalRange, useConfirmMeal } from './MealBits'
import { MealPhotos } from './MealPhotos'
import type { Meal, MealItem } from '@/types'

/** One meal to look at: the totals first, then what it was made of, item by item.
 * Every number in the list is for the portion; the label density sits beside the weight. */
export function MealView({
  meal,
  onEdit,
  onClose,
}: {
  meal: Meal
  onEdit: () => void
  onClose: () => void
}) {
  const user = useUser()
  const client = useQueryClient()
  const confirm = useConfirmMeal()
  const [deleting, setDeleting] = useState(false)
  const draft = meal.status === 'draft'
  const range = kcalRange(meal)
  const day = dayLabel(meal.eaten_on, todayIn(user.timezone))

  const remove = useMutation({
    mutationFn: () => mealsApi.remove(meal.id),
    onSuccess: async () => {
      client.removeQueries({ queryKey: keys.meal(meal.id) })
      await invalidateMeals(client)
      toast.success('Запись удалена')
      onClose()
    },
    // Storage cleanup can fail after the record is gone: show the truth either way.
    onError: () => invalidateMeals(client),
    meta: { silent: true },
  })

  return (
    <div className="flex flex-col gap-5">
      {draft && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[14px] border border-dashed border-warning/60 bg-warning-soft px-4 py-3">
          <p className="text-sm">
            <span className="font-medium">Черновик.</span> Не учитывается в итогах дня.
          </p>
          <Button size="sm" onClick={() => confirm.mutate(meal.id)} disabled={confirm.isPending}>
            <Check />
            Сохранить в дневник
          </Button>
        </div>
      )}

      {meal.photos.length > 0 && <MealPhotos meal={meal} />}

      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          {mealTypeLabel(meal.meal_type)}, {day.toLowerCase()}, {timeOf(meal.eaten_at)}
        </p>
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="hero-number">{num(meal.kcal)}</span>
          <span className="text-lg text-muted-foreground">ккал</span>
          {range && <span className="text-sm text-muted-foreground">диапазон {range}</span>}
        </p>
        <dl className="grid grid-cols-3 gap-2">
          {MACROS.map((macro) => (
            <div key={macro.key} className="rounded-[14px] bg-muted px-3 py-2.5">
              <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={`macro-dot bg-macro-${macro.key}`} aria-hidden="true" />
                {macro.label}
              </dt>
              <dd className="serif-number mt-0.5 text-xl leading-tight">
                {num(meal[macro.key])}{' '}
                <span className="font-sans text-xs font-normal text-muted-foreground">г</span>
              </dd>
            </div>
          ))}
        </dl>
        <ConfidenceBadge meal={meal} className="self-start" />
      </div>

      {meal.ai_comment && (
        <div className="rounded-r-[12px] border-l-[3px] border-primary bg-accent/60 px-3.5 py-2.5 text-[15px] leading-snug">
          <p className="mb-0.5 text-xs font-medium text-accent-foreground">Ассистент</p>
          {meal.ai_comment}
        </div>
      )}

      <section aria-labelledby="meal-items" className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h3 id="meal-items" className="text-sm font-medium">
            Состав
          </h3>
          <span className="text-xs text-muted-foreground">КБЖУ на порцию</span>
        </div>
        {meal.items.length ? (
          <ul className="row-list overflow-hidden rounded-[16px] border bg-card">
            {meal.items.map((item) => (
              <ItemRow key={item.id} item={item} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Состав не записан.</p>
        )}
      </section>

      {meal.photos.length === 0 && <MealPhotos meal={meal} compact />}

      {meal.estimated_by === 'ai' && meal.assumptions.length > 0 && (
        <details className="rounded-[14px] bg-muted px-4 py-1.5 text-sm">
          <summary className="flex min-h-9 cursor-pointer items-center text-muted-foreground select-none">
            Из чего исходил AI ({meal.assumptions.length})
          </summary>
          <ul className="list-disc space-y-0.5 pb-2 pl-5 text-muted-foreground">
            {meal.assumptions.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </details>
      )}

      {meal.note && (
        <div className="text-sm">
          <p className="text-muted-foreground">Заметка</p>
          <p className="whitespace-pre-line">{meal.note}</p>
        </div>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Button
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => setDeleting(true)}
        >
          <Trash2 />
          Удалить запись
        </Button>
        <Button variant={draft ? 'outline' : 'default'} onClick={onEdit} className="sm:min-w-40">
          <PencilLine />
          Изменить
        </Button>
      </div>

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Удалить «${meal.title}»?`}
        description="Запись и ее фото удалятся без возможности восстановления."
        onConfirm={() => remove.mutateAsync()}
      />
    </div>
  )
}

function ItemRow({ item }: { item: MealItem }) {
  const per100 = item.grams ? (item.kcal * 100) / item.grams : null
  return (
    <li className="flex items-start justify-between gap-3 px-3.5 py-3">
      <div className="min-w-0">
        <p className="leading-snug font-medium">
          {item.name}
          {item.product_id !== null && (
            <Tag
              className="ml-1.5 inline size-3.5 align-[-2px] text-accent-foreground"
              aria-label="мой продукт"
            />
          )}
        </p>
        <p className="mt-0.5 text-[13px] text-muted-foreground tabular">
          {item.grams === null
            ? 'вес не указан'
            : `${itemWeight(item)}, ${num(per100)} ккал на 100 г`}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end">
        <p className="serif-number text-[17px] leading-tight whitespace-nowrap">
          {num(item.kcal)}{' '}
          <span className="font-sans text-xs font-normal text-muted-foreground">ккал</span>
        </p>
        <MacroLine
          value={item}
          className="mt-1 justify-end gap-x-2 text-xs text-muted-foreground"
        />
      </div>
    </li>
  )
}
