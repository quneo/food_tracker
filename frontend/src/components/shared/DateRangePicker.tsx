import { useState, type ReactNode } from 'react'
import { CalendarDays } from 'lucide-react'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import type { DateRange } from 'react-day-picker'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { useDesktop } from '@/hooks/useMediaQuery'
import { addDays, cap, dateToDay, dayToDate, diffDays, rangeLabel } from '@/lib/format'
import { ResponsiveSheet } from './ResponsiveSheet'

const LABELS = {
  labelPrevious: () => 'Предыдущий месяц',
  labelNext: () => 'Следующий месяц',
  labelNav: () => 'Переключение месяцев',
}

/** Picks a period of at most `maxDays` days ending no later than `today`. */
export function DateRangePicker({
  from,
  to,
  today,
  onChange,
  maxDays = 400,
  label,
  variant = 'outline',
  className,
}: {
  from?: string
  to?: string
  today: string
  onChange: (from: string, to: string) => void
  maxDays?: number
  label?: ReactNode
  variant?: 'outline' | 'ghost'
  className?: string
}) {
  const desktop = useDesktop()
  const [open, setOpen] = useState(false)
  const [range, setRange] = useState<DateRange | undefined>()

  function show(value: boolean) {
    if (value) setRange(from && to ? { from: dayToDate(from), to: dayToDate(to) } : undefined)
    setOpen(value)
  }

  const start = range?.from ? dateToDay(range.from) : null
  const end = range?.to ? dateToDay(range.to) : start
  const tooLong = start && end ? diffDays(end, start) > maxDays : false

  const picker = (
    <div className="flex flex-col gap-3">
      <Calendar
        mode="range"
        locale={ru}
        labels={LABELS}
        selected={range}
        onSelect={setRange}
        numberOfMonths={1}
        defaultMonth={range?.from ?? dayToDate(to ?? today)}
        disabled={{ after: dayToDate(today) }}
        className="mx-auto bg-transparent p-0"
        formatters={{ formatCaption: (month) => cap(format(month, 'LLLL yyyy', { locale: ru })) }}
      />
      {tooLong && <p className="form-error">Период не длиннее {maxDays} дней</p>}
      <Button
        className="w-full"
        disabled={!start || !end || tooLong}
        onClick={() => {
          if (!start || !end) return
          onChange(start, end)
          setOpen(false)
        }}
      >
        Показать {start && end ? rangeLabel(start, end) : ''}
      </Button>
    </div>
  )

  const trigger = (
    <Button
      variant={variant}
      className={className}
      onClick={desktop ? undefined : () => show(true)}
    >
      <CalendarDays />
      {label ?? (from && to ? rangeLabel(from, to) : 'Период')}
    </Button>
  )

  if (desktop)
    return (
      <Popover open={open} onOpenChange={show}>
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
        <PopoverContent className="w-auto p-3" align="start">
          {picker}
        </PopoverContent>
      </Popover>
    )
  return (
    <>
      {trigger}
      <ResponsiveSheet open={open} onOpenChange={show} title="Период">
        {picker}
      </ResponsiveSheet>
    </>
  )
}

export const lastDays = (today: string, count: number) => ({
  from: addDays(today, -(count - 1)),
  to: today,
})
