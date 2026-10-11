import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { mealsApi } from '@/api/endpoints'
import { invalidateMeals } from '@/api/keys'
import { Badge } from '@/components/ui/badge'
import { CONFIDENCE, MACROS } from '@/lib/labels'
import { num } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Confidence, Meal, Totals } from '@/types'

const CONFIDENCE_TONE: Record<Confidence, string> = {
  low: 'bg-warning-soft text-warning',
  medium: 'bg-muted text-muted-foreground',
  high: 'bg-accent text-accent-foreground',
}

/** Shown only for numbers the assistant estimated. */
export function ConfidenceBadge({ meal, className }: { meal: Meal; className?: string }) {
  if (meal.estimated_by !== 'ai') return null
  const label = meal.confidence
    ? `оценка AI: ${CONFIDENCE[meal.confidence]} уверенность`
    : 'оценка AI'
  return (
    <Badge
      variant="secondary"
      className={cn(
        'h-6 gap-1 px-2 text-xs font-normal whitespace-normal',
        meal.confidence && CONFIDENCE_TONE[meal.confidence],
        className,
      )}
    >
      <Sparkles aria-hidden="true" />
      {label}
    </Badge>
  )
}

export function DraftBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn('h-6 border-dashed border-warning/60 px-2 text-xs text-warning', className)}
    >
      Черновик
    </Badge>
  )
}

/** "Б 32 · Ж 12 · У 45" with a colored mark beside each letter. */
export function MacroLine({ value, className }: { value: Totals; className?: string }) {
  return (
    <span className={cn('inline-flex flex-wrap items-center gap-x-3 gap-y-1 tabular', className)}>
      {MACROS.map((macro) => (
        <span key={macro.key} className="inline-flex items-center gap-1.5">
          <span className={`macro-dot bg-macro-${macro.key}`} aria-hidden="true" />
          <span>
            <abbr title={macro.label} className="no-underline">
              {macro.short}
            </abbr>{' '}
            {num(value[macro.key])}
          </span>
        </span>
      ))}
    </span>
  )
}

/** "450–620 ккал" when the assistant gave a range. */
export function kcalRange(meal: Meal) {
  if (meal.estimated_by !== 'ai' || meal.kcal_low === null || meal.kcal_high === null) return ''
  return `${num(meal.kcal_low)}–${num(meal.kcal_high)} ккал`
}

export function useConfirmMeal() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => mealsApi.confirm(id),
    onSuccess: () => {
      toast.success('Сохранено в дневнике')
      return invalidateMeals(client)
    },
  })
}
