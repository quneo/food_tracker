import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { addDays, cap, formatDay, num } from '@/lib/format'
import type { DailyRow } from '@/types'

/** The week's calories as bars; the chosen day in lime with its share of the target. */
export function WeekBars({
  start,
  today,
  selected,
  rows,
  target,
  onSelect,
}: {
  start: string
  today: string
  selected: string
  rows: DailyRow[] | undefined
  target: number | null
  onSelect: (day: string) => void
}) {
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index))
  const byDay = new Map(rows?.map((row) => [row.day, row]))
  const values = days.map((day) => byDay.get(day)?.kcal ?? 0)
  const top = Math.max(target ? target * 1.15 : 0, ...values.map((value) => value * 1.08), 1)
  const logged = days.filter((day) => (byDay.get(day)?.meals ?? 0) > 0)
  const average = logged.length
    ? logged.reduce((sum, day) => sum + (byDay.get(day)?.kcal ?? 0), 0) / logged.length
    : null
  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle>Неделя</CardTitle>
        {average !== null && (
          <CardAction className="text-sm text-muted-foreground tabular">
            в среднем {num(average)} ккал
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        <div className="week-bars">
          {target && (
            <span
              className="week-target"
              style={{ bottom: `calc(20px + (100% - 46px) * ${target / top})` }}
              aria-hidden="true"
            />
          )}
          {days.map((day, index) => {
            const value = values[index]
            const chosen = day === selected
            const over = target !== null && value > target * 1.1
            return (
              <button
                key={day}
                type="button"
                className="week-bar"
                aria-pressed={chosen}
                disabled={day > today}
                onClick={() => onSelect(day)}
                aria-label={`${formatDay(day, 'EEEE, d MMMM')}: ${num(value)} ккал`}
              >
                <span className="bar-column">
                  <span
                    className={over ? 'bar-value is-over' : 'bar-value'}
                    style={{ height: `${(value / top) * 100}%` }}
                  >
                    {chosen && value > 0 && (
                      <span className="bar-pill">
                        {target ? `${Math.round((value / target) * 100)}%` : num(value)}
                      </span>
                    )}
                  </span>
                </span>
                <span>{cap(formatDay(day, 'EEEEEE'))}</span>
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
