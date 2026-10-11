import { useState } from 'react'
import { Check, PencilLine } from 'lucide-react'
import { Photo } from '@/components/shared/Photo'
import { Lightbox } from '@/components/shared/Lightbox'
import { mealTypeLabel } from '@/lib/labels'
import { itemWeight, num, timeOf } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ConfidenceBadge, DraftBadge, MacroLine, kcalRange, useConfirmMeal } from './MealBits'
import type { Meal } from '@/types'

/** A meal in the diary, drawn as a message: photos on top, the numbers, the time in the
 * corner. A draft gets buttons underneath, like a bot's inline keyboard. */
export function MealCard({
  meal,
  onOpen,
}: {
  meal: Meal
  onOpen: (id: number, edit?: boolean) => void
}) {
  const [viewing, setViewing] = useState<number | null>(null)
  const confirm = useConfirmMeal()
  const draft = meal.status === 'draft'
  const range = kcalRange(meal)
  const ids = meal.photos.map((photo) => photo.id)
  const shown = meal.photos.slice(0, 3)
  return (
    <div className="flex w-full flex-col items-start gap-1.5">
      <article
        className={cn('bubble', draft && 'is-draft')}
        aria-label={`${meal.title}, ${timeOf(meal.eaten_at)}`}
      >
        {shown.length > 0 && (
          <div
            className="bubble-media"
            style={{ gridTemplateColumns: `repeat(${Math.min(shown.length, 3)}, minmax(0, 1fr))` }}
          >
            {shown.map((photo, index) => (
              <button
                key={photo.id}
                type="button"
                className="relative"
                onClick={() => setViewing(index)}
                aria-label={`Фото ${index + 1} из ${meal.photos.length}`}
              >
                <Photo
                  id={photo.id}
                  alt=""
                  className={cn('w-full', shown.length === 1 ? 'aspect-[4/3]' : 'aspect-square')}
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
          className="block w-full px-4 pt-3 pb-2.5 text-left transition-colors hover:bg-muted/50"
        >
          <span className="flex items-start justify-between gap-3">
            <span className="min-w-0 font-semibold leading-snug">{meal.title}</span>
            <span className="serif-number shrink-0 text-lg leading-tight whitespace-nowrap">
              {num(meal.kcal)} <span className="font-sans text-xs font-normal">ккал</span>
            </span>
          </span>
          <MacroLine value={meal} className="mt-1 text-[13px] text-muted-foreground" />
          {meal.items.length > 0 && (
            <span className="mt-2 block text-sm leading-relaxed">
              {meal.items.map((item, index) => (
                <span key={item.id}>
                  {index > 0 && ', '}
                  {item.name}
                  {item.grams !== null && (
                    <span className="whitespace-nowrap text-muted-foreground">
                      {' '}
                      {itemWeight(item)}
                    </span>
                  )}
                </span>
              ))}
            </span>
          )}
          {meal.ai_comment && (
            <span className="mt-2.5 block rounded-r-[10px] border-l-[3px] border-primary bg-accent/60 py-1.5 pr-2.5 pl-2.5 text-sm leading-snug">
              <span className="block text-xs font-medium text-accent-foreground">Ассистент</span>
              {meal.ai_comment}
            </span>
          )}
          {(draft || meal.estimated_by === 'ai') && (
            <span className="mt-2.5 flex flex-wrap items-center gap-2">
              {draft && <DraftBadge />}
              <ConfidenceBadge meal={meal} />
              {range && <span className="text-xs text-muted-foreground">{range}</span>}
            </span>
          )}
          {meal.note && (
            <span className="mt-2 block text-sm text-muted-foreground italic">{meal.note}</span>
          )}
          <span className="bubble-time">
            {mealTypeLabel(meal.meal_type)}, {timeOf(meal.eaten_at)}
          </span>
          <span className="block clear-both" />
        </button>
        {meal.estimated_by === 'ai' && meal.assumptions.length > 0 && (
          <details className="border-t px-4 py-1.5 text-sm">
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
      </article>
      {draft && (
        <div className="inline-keys">
          <button
            type="button"
            onClick={() => confirm.mutate(meal.id)}
            disabled={confirm.isPending}
          >
            <Check aria-hidden="true" />
            Сохранить
          </button>
          <button type="button" onClick={() => onOpen(meal.id, true)}>
            <PencilLine aria-hidden="true" />
            Исправить
          </button>
        </div>
      )}
      <Lightbox
        ids={ids}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title={meal.title}
      />
    </div>
  )
}
