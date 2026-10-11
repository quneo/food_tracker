import { Check, Utensils } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Photo } from '@/components/shared/Photo'
import { mealTypeLabel } from '@/lib/labels'
import { num, timeOf } from '@/lib/format'
import { DraftBadge, useConfirmMeal } from './MealBits'
import type { Meal } from '@/types'

/** A compact line for the day's meals on the home screen. */
export function MealRow({ meal, onOpen }: { meal: Meal; onOpen: (id: number) => void }) {
  const confirm = useConfirmMeal()
  const draft = meal.status === 'draft'
  return (
    <div className="flex items-center">
      <button type="button" className="list-button min-w-0 flex-1" onClick={() => onOpen(meal.id)}>
        {meal.photos[0] ? (
          <Photo id={meal.photos[0].id} alt="" className="thumb" />
        ) : (
          <span className="thumb grid place-items-center text-muted-foreground" aria-hidden="true">
            <Utensils className="size-5" />
          </span>
        )}
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-muted-foreground">
            <span className="tabular">{timeOf(meal.eaten_at)}</span>
            <span>{mealTypeLabel(meal.meal_type)}</span>
            {draft && <DraftBadge className="h-5" />}
          </span>
          <span className="truncate font-medium">{meal.title}</span>
        </span>
        <span
          className={
            draft
              ? 'font-medium whitespace-nowrap text-muted-foreground'
              : 'font-medium whitespace-nowrap'
          }
        >
          {num(meal.kcal)} ккал
        </span>
      </button>
      {draft && (
        <Button
          size="sm"
          variant="outline"
          className="mr-4 ml-1 shrink-0"
          onClick={() => confirm.mutate(meal.id)}
          disabled={confirm.isPending}
          aria-label={`Сохранить «${meal.title}» в дневник`}
        >
          <Check />
          <span className="hidden sm:inline">Сохранить</span>
        </Button>
      )}
    </div>
  )
}
