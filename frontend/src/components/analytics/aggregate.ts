import { endOfWeek, startOfWeek } from 'date-fns'
import { dateToDay, dayToDate, formatDay, rangeLabel } from '@/lib/format'
import type { DailyRow, DayStatus } from '@/types'

export type Grouping = 'day' | 'week' | 'month'

export interface Bucket {
  key: string
  label: string
  title: string
  start: string
  end: string
  /** complete: built from counted days; partial: only from partial days; empty: a gap. */
  status: DayStatus
  kcal: number | null
  protein: number | null
  fat: number | null
  carbs: number | null
  weight: number | null
  /** Days the values were averaged over. */
  counted: number
  logged: number
  total: number
  rows: DailyRow[]
}

const average = (rows: DailyRow[], field: 'kcal' | 'protein' | 'fat' | 'carbs' | 'weight') => {
  const values = rows.map((row) => row[field]).filter((value): value is number => value !== null)
  return values.length
    ? Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10
    : null
}

function bucketKey(day: string, grouping: Grouping) {
  const date = dayToDate(day)
  if (grouping === 'week') return dateToDay(startOfWeek(date, { weekStartsOn: 1 }))
  if (grouping === 'month') return day.slice(0, 7)
  return day
}

/**
 * Daily rows -> chart points. A day shows its own numbers (empty days are gaps); weeks and
 * months show the average over counted days: complete ones, plus partial ones on request.
 */
export function aggregate(rows: DailyRow[], grouping: Grouping, includePartial: boolean): Bucket[] {
  const groups = new Map<string, DailyRow[]>()
  for (const row of rows) {
    const key = bucketKey(row.day, grouping)
    const list = groups.get(key) ?? []
    list.push(row)
    groups.set(key, list)
  }
  return [...groups.entries()].map(([key, list]) => {
    const logged = list.filter((row) => row.status !== 'empty')
    const counted = logged.filter((row) => row.status === 'complete' || includePartial)
    const source = counted.length ? counted : logged
    const status: DayStatus = counted.length
      ? grouping === 'day' && list[0].status === 'partial'
        ? 'partial'
        : 'complete'
      : logged.length
        ? 'partial'
        : 'empty'
    const start = grouping === 'day' ? key : list[0].day
    const end = list[list.length - 1].day
    let label: string
    let title: string
    if (grouping === 'day') {
      label = formatDay(key, 'd.MM')
      title = formatDay(key, 'EEEEEE, d MMMM')
    } else if (grouping === 'week') {
      const weekStart = key
      const weekEnd = dateToDay(endOfWeek(dayToDate(key), { weekStartsOn: 1 }))
      label = formatDay(weekStart, 'd.MM')
      title = `Неделя ${rangeLabel(weekStart, weekEnd)}`
    } else {
      label = formatDay(`${key}-01`, 'LLL')
      title = formatDay(`${key}-01`, 'LLLL yyyy')
    }
    return {
      key,
      label,
      title,
      start,
      end,
      status,
      kcal: status === 'empty' ? null : average(source, 'kcal'),
      protein: status === 'empty' ? null : average(source, 'protein'),
      fat: status === 'empty' ? null : average(source, 'fat'),
      carbs: status === 'empty' ? null : average(source, 'carbs'),
      weight: average(list, 'weight'),
      counted: counted.length,
      logged: logged.length,
      total: list.length,
      rows: list,
    }
  })
}

export function defaultGrouping(days: number): Grouping {
  if (days <= 45) return 'day'
  if (days <= 190) return 'week'
  return 'month'
}

export const STATUS_LABEL: Record<DayStatus, string> = {
  empty: 'Нет записей',
  partial: 'Неполный день',
  complete: 'Полный день',
}
