import { Check, Utensils } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Photo } from '@/components/shared/Photo'
import { mealTypeLabel } from '@/lib/labels'
import { num, timeOf } from '@/lib/format'
import { cn } from '@/lib/utils'
import { DraftBadge, MacroLine, useConfirmMeal } from './MealBits'
import type { Meal } from '@/types'

/** A meal as a row of a chat list: round photo, title and macros, time and calories. */
export function MealRow({ meal, onOpen }: { meal: Meal; onOpen: (id: number) => void }) {
  const confirm = useConfirmMeal()
  const draft = meal.status === 'draft'
  return (
    <div className="flex items-center">
      <button type="button" className="chat-row min-w-0 flex-1" onClick={() => onOpen(meal.id)}>
        {meal.photos[0] ? (
          <Photo id={meal.photos[0].id} alt="" className="chat-avatar" />
        ) : (
          <span className="chat-avatar is-empty" aria-hidden="true">
            <Utensils className="size-5" />
          </span>
        )}
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate font-medium">{meal.title}</span>
            {draft && <DraftBadge className="h-5 shrink-0" />}
          </span>
          <MacroLine value={meal} className="text-[13px] text-muted-foreground" />
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-xs text-muted-foreground">
            {/* A narrow phone keeps the room for the title and macros. */}
            <span className="max-[420px]:hidden">{mealTypeLabel(meal.meal_type)}, </span>
            <span className="tabular">{timeOf(meal.eaten_at)}</span>
          </span>
          <span className={cn('serif-number text-[17px]', draft && 'text-muted-foreground')}>
            {num(meal.kcal)} <span className="font-sans text-xs font-normal">ккал</span>
          </span>
        </span>
      </button>
      {draft && (
        <Button
          size="icon"
          variant="outline"
          className="mr-3 shrink-0 rounded-full"
          onClick={() => confirm.mutate(meal.id)}
          disabled={confirm.isPending}
          aria-label={`Сохранить «${meal.title}» в дневник`}
          title="Сохранить в дневник"
        >
          <Check />
        </Button>
      )}
    </div>
  )
}
