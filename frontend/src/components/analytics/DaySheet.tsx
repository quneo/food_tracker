import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { analyticsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { MacroLine } from '@/components/meals/MealBits'
import { cap, formatDay, num } from '@/lib/format'
import { cn } from '@/lib/utils'
import { STATUS_LABEL } from './aggregate'
import type { DailyRow } from '@/types'

const CHOICES: { value: 'auto' | 'complete' | 'partial'; label: string; hint: string }[] = [
  {
    value: 'auto',
    label: 'Автоматически',
    hint: 'Полный, если записано 2+ приема и хотя бы половина цели',
  },
  { value: 'complete', label: 'Полный', hint: 'Записано все, что съедено' },
  { value: 'partial', label: 'Неполный', hint: 'Что-то не записано — не учитывать в средних' },
]

/** One day's numbers and whether it counts as fully logged. */
export function DaySheet({ row, onClose }: { row: DailyRow | null; onClose: () => void }) {
  const client = useQueryClient()
  const mark = useMutation({
    mutationFn: (value: boolean | null) => analyticsApi.markDay(row!.day, value),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: keys.daily }),
        client.invalidateQueries({ queryKey: keys.report }),
      ])
      toast.success('Отметка сохранена')
      onClose()
    },
  })
  const current = !row
    ? 'auto'
    : !row.marked
      ? 'auto'
      : row.status === 'complete'
        ? 'complete'
        : 'partial'
  return (
    <ResponsiveSheet
      open={row !== null}
      onOpenChange={(value) => !value && onClose()}
      title={row ? cap(formatDay(row.day, 'EEEE, d MMMM yyyy')) : ''}
      description={
        row ? STATUS_LABEL[row.status] + (row.marked ? ' — отмечено вами' : '') : undefined
      }
    >
      {row && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2 rounded-[14px] bg-muted px-4 py-3">
            <p className="text-2xl font-semibold tracking-tight">{num(row.kcal)} ккал</p>
            <MacroLine value={row} className="text-sm text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Приемов пищи: {row.meals}
              {row.weight !== null && ` · вес ${num(row.weight, 1)} кг`}
            </p>
          </div>
          {row.meals > 0 && (
            <div className="flex flex-col gap-2" role="radiogroup" aria-labelledby="day-mark-label">
              <span id="day-mark-label" className="text-sm font-medium">
                Как учитывать день
              </span>
              {CHOICES.map((choice) => (
                <button
                  key={choice.value}
                  type="button"
                  role="radio"
                  aria-checked={current === choice.value}
                  disabled={mark.isPending}
                  onClick={() =>
                    mark.mutate(choice.value === 'auto' ? null : choice.value === 'complete')
                  }
                  className={cn(
                    'flex min-h-14 flex-col items-start rounded-[14px] border px-4 py-2.5 text-left transition-colors hover:bg-muted',
                    current === choice.value && 'border-primary bg-accent hover:bg-accent',
                  )}
                >
                  <span className="font-medium">{choice.label}</span>
                  <span className="text-sm text-muted-foreground">{choice.hint}</span>
                </button>
              ))}
            </div>
          )}
          <Link
            to={`/diary?from=${row.day}&to=${row.day}`}
            className="inline-flex min-h-11 items-center gap-1 self-start text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            Записи за день
            <ArrowRight className="size-4" />
          </Link>
        </div>
      )}
    </ResponsiveSheet>
  )
}
