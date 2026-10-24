import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { addDays, cap, formatDay, num } from '@/lib/format'
import type { DailyRow } from '@/types'

/** Monday of the week the day is in. */
export function weekStart(day: string) {
  const weekday = (new Date(`${day}T12:00:00`).getDay() + 6) % 7
  return addDays(day, -weekday)
}

const RING = 2 * Math.PI * 17

/** A week as day rings: each ring fills with the day's calories against the target. */
export function WeekStrip({
  start,
  today,
  selected,
  rows,
  target,
  onSelect,
  onWeek,
}: {
  start: string
  today: string
  selected: string
  rows: DailyRow[] | undefined
  target: number | null
  onSelect: (day: string) => void
  onWeek: (start: string) => void
}) {
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index))
  const byDay = new Map(rows?.map((row) => [row.day, row]))
  const end = days[6]
  const month =
    start.slice(5, 7) === end.slice(5, 7)
      ? formatDay(start, 'LLLL yyyy')
      : `${formatDay(start, 'LLL')} – ${formatDay(end, 'LLL yyyy')}`
  return (
    <section
      className="glass flex flex-col gap-2 rounded-[24px] px-3 pt-3 pb-2"
      aria-label="Неделя"
    >
      <div className="flex items-center justify-between gap-2 pl-2">
        <h2 className="section-title">{cap(month)}</h2>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={() => onWeek(addDays(start, -7))}
            aria-label="Прошлая неделя"
          >
            <ChevronLeft />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={() => onWeek(addDays(start, 7))}
            disabled={addDays(start, 7) > today}
            aria-label="Следующая неделя"
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div className="week-strip">
        {days.map((day) => {
          const row = byDay.get(day)
          const share = target && row ? row.kcal / target : 0
          const label = formatDay(day, 'EEEEEE')
          return (
            <button
              key={day}
              type="button"
              className="day-cell"
              aria-pressed={day === selected}
              aria-current={day === today ? 'date' : undefined}
              disabled={day > today}
              onClick={() => onSelect(day)}
              aria-label={`${formatDay(day, 'EEEE, d MMMM')}${
                row?.meals ? `: ${num(row.kcal)} ккал` : ''
              }`}
            >
              <span className="day-label">{cap(label)}</span>
              <span className="day-ring">
                <svg viewBox="0 0 40 40" aria-hidden="true">
                  <circle cx="20" cy="20" r="17" strokeWidth="3" className="ring-bg" />
                  {share > 0 && (
                    <circle
                      cx="20"
                      cy="20"
                      r="17"
                      strokeWidth="3"
                      className={share > 1.1 ? 'ring-fill is-over' : 'ring-fill'}
                      strokeDasharray={RING}
                      strokeDashoffset={RING * (1 - Math.min(share, 1))}
                    />
                  )}
                </svg>
                <span>{Number(day.slice(8))}</span>
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
