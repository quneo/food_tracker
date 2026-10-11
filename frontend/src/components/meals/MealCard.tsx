import { useState } from 'react'
import { Check, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Photo } from '@/components/shared/Photo'
import { Lightbox } from '@/components/shared/Lightbox'
import { mealTypeLabel } from '@/lib/labels'
import { itemWeight, num, timeOf } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ConfidenceBadge, DraftBadge, MacroLine, kcalRange, useConfirmMeal } from './MealBits'
import type { Meal } from '@/types'

/** A meal in the diary feed: everything at a glance, the editor one tap away. */
export function MealCard({ meal, onOpen }: { meal: Meal; onOpen: (id: number) => void }) {
  const [viewing, setViewing] = useState<number | null>(null)
  const confirm = useConfirmMeal()
  const draft = meal.status === 'draft'
  const range = kcalRange(meal)
  const ids = meal.photos.map((photo) => photo.id)
  return (
    <article
      className={cn(
        'overflow-hidden rounded-[20px] border bg-card shadow-[var(--card-shadow)]',
        draft && 'border-dashed border-warning/60',
      )}
      aria-label={`${meal.title}, ${timeOf(meal.eaten_at)}`}
    >
      {meal.photos.length > 0 && (
        <div className="flex gap-1.5 px-3 pt-3">
          {meal.photos.slice(0, 3).map((photo, index) => (
            <button
              key={photo.id}
              type="button"
              className="relative min-w-0 flex-1 overflow-hidden rounded-[14px]"
              onClick={() => setViewing(index)}
              aria-label={`Фото ${index + 1} из ${meal.photos.length}`}
            >
              <Photo
                id={photo.id}
                alt=""
                className={cn(
                  'w-full',
                  meal.photos.length === 1 ? 'aspect-[16/9]' : 'aspect-square',
                )}
              />
              {index === 2 && meal.photos.length > 3 && (
                <span className="absolute inset-0 grid place-items-center bg-black/45 text-lg font-medium text-white">
                  +{meal.photos.length - 3}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => onOpen(meal.id)}
        className="group flex w-full flex-col gap-2 px-4 pt-3 pb-4 text-left transition-colors hover:bg-muted/60 sm:px-5"
      >
        <span className="flex w-full items-start gap-3">
          <span className="block min-w-0 flex-1">
            <span className="block text-sm text-muted-foreground">
              <span className="tabular">{timeOf(meal.eaten_at)}</span> ·{' '}
              {mealTypeLabel(meal.meal_type)}
            </span>
            <span className="block text-base leading-snug font-semibold">{meal.title}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1">
            <span className="text-base font-semibold whitespace-nowrap">{num(meal.kcal)} ккал</span>
            <ChevronRight
              className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </span>
        </span>
        <MacroLine value={meal} className="text-sm text-muted-foreground" />
        {meal.items.length > 0 && (
          <span className="block text-sm">
            {meal.items.map((item, index) => (
              <span key={item.id}>
                {index > 0 && <span className="text-muted-foreground"> · </span>}
                {item.name}
                {item.grams !== null && (
                  <span className="text-muted-foreground whitespace-nowrap">
                    {' '}
                    {itemWeight(item)}
                  </span>
                )}
              </span>
            ))}
          </span>
        )}
        {(draft || meal.estimated_by === 'ai') && (
          <span className="flex flex-wrap items-center gap-2">
            {draft && <DraftBadge />}
            <ConfidenceBadge meal={meal} />
            {range && <span className="text-xs text-muted-foreground">{range}</span>}
          </span>
        )}
        {meal.note && (
          <span className="block text-sm text-muted-foreground italic">{meal.note}</span>
        )}
      </button>
      {meal.estimated_by === 'ai' && meal.assumptions.length > 0 && (
        <details className="border-t px-4 py-2 text-sm sm:px-5">
          <summary className="flex min-h-9 cursor-pointer items-center text-muted-foreground select-none">
            Допущения AI ({meal.assumptions.length})
          </summary>
          <ul className="list-disc space-y-0.5 pb-2 pl-5 text-muted-foreground">
            {meal.assumptions.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </details>
      )}
      {draft && (
        <div className="flex items-center justify-between gap-3 border-t px-4 py-2.5 sm:px-5">
          <span className="text-sm text-muted-foreground">Не учтено в итогах</span>
          <Button size="sm" onClick={() => confirm.mutate(meal.id)} disabled={confirm.isPending}>
            <Check />
            Сохранить
          </Button>
        </div>
      )}
      <Lightbox
        ids={ids}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title={meal.title}
      />
    </article>
  )
}
