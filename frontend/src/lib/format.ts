import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import type { MealItem } from '@/types'

const numberFormats = new Map<number, Intl.NumberFormat>()
function numberFormat(digits: number) {
  let value = numberFormats.get(digits)
  if (!value) {
    value = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits })
    numberFormats.set(digits, value)
  }
  return value
}

/** 1840 -> "1 840", 82.45 -> "82,5" (digits = max fraction digits). */
export const num = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : numberFormat(digits).format(value)

export const kcal = (value: number | null | undefined) => `${num(value)} ккал`
export const grams = (value: number | null | undefined) => `${num(value)} г`
export const kg = (value: number | null | undefined) => `${num(value, 1)} кг`

/** "+1,2" / "−0,4" / "0" with a real minus sign. */
export function signed(value: number, digits = 1) {
  const rounded = Number(value.toFixed(digits))
  if (rounded === 0) return '0'
  return `${rounded > 0 ? '+' : '−'}${num(Math.abs(rounded), digits)}`
}

/** A guessed weight is never shown as exact. */
export function itemWeight(item: Pick<MealItem, 'grams' | 'grams_source'>) {
  if (item.grams === null) return ''
  return `${item.grams_source === 'estimated' ? '~' : ''}${num(item.grams)} г`
}

export function plural(value: number, forms: [string, string, string]) {
  const n = Math.abs(value) % 100
  const last = n % 10
  if (n > 10 && n < 20) return forms[2]
  if (last > 1 && last < 5) return forms[1]
  if (last === 1) return forms[0]
  return forms[2]
}

export const days = (value: number) => `${value} ${plural(value, ['день', 'дня', 'дней'])}`

// Times from the API are wall times in the person's zone ("2026-10-11T13:20+07:00"):
// they are shown as written, never converted into the browser's zone.
export const timeOf = (iso: string) => iso.slice(11, 16)
export const dayOf = (iso: string) => iso.slice(0, 10)
/** Value for <input type="datetime-local">: "2026-10-11T13:20". */
export const localInput = (iso: string) => iso.slice(0, 16)

/** A calendar day as a Date at local noon, only for formatting and calendars. */
export function dayToDate(day: string) {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date, 12)
}

export const dateToDay = (date: Date) => format(date, 'yyyy-MM-dd')

export const formatDay = (day: string, pattern: string) =>
  format(dayToDate(day), pattern, { locale: ru })

export function addDays(day: string, amount: number) {
  const date = dayToDate(day)
  date.setDate(date.getDate() + amount)
  return dateToDay(date)
}

export function diffDays(later: string, earlier: string) {
  return Math.round((dayToDate(later).getTime() - dayToDate(earlier).getTime()) / 86_400_000)
}

function partsIn(timeZone: string) {
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }
  try {
    return new Intl.DateTimeFormat('sv-SE', { ...options, timeZone }).format(new Date())
  } catch {
    return new Intl.DateTimeFormat('sv-SE', options).format(new Date())
  }
}

/** Today's date in the person's own time zone: "2026-10-11". */
export const todayIn = (timeZone: string) => partsIn(timeZone).slice(0, 10)
/** Now in the person's own time zone for datetime-local inputs: "2026-10-11T13:20". */
export const nowIn = (timeZone: string) => partsIn(timeZone).replace(' ', 'T').slice(0, 16)

/** "Сегодня", "Вчера", "пн, 6 окт", "пн, 6 окт 2025". */
export function dayLabel(day: string, today: string) {
  if (day === today) return 'Сегодня'
  if (day === addDays(today, -1)) return 'Вчера'
  return formatDay(
    day,
    day.slice(0, 4) === today.slice(0, 4) ? 'EEEEEE, d MMM' : 'EEEEEE, d MMM yyyy',
  )
}

export function rangeLabel(from: string, to: string) {
  if (from === to) return formatDay(from, 'd MMM yyyy')
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  return `${formatDay(from, sameYear ? 'd MMM' : 'd MMM yyyy')} – ${formatDay(to, 'd MMM yyyy')}`
}

/** "2026-10-11T13:20+07:00" -> "11 окт, 13:20" (wall time as given). */
export function dateTimeLabel(iso: string, today?: string) {
  const day = dayOf(iso)
  const head = today ? dayLabel(day, today) : formatDay(day, 'd MMM yyyy')
  return `${head}, ${timeOf(iso)}`
}

/** Admin and memory timestamps are naive UTC: shown in the browser's zone. */
export function utcLabel(value: string | null, withTime = true) {
  if (!value) return '—'
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return '—'
  return format(date, withTime ? 'd MMM yyyy, HH:mm' : 'd MMM yyyy', { locale: ru })
}

/** Accepts "82,4" and "82.4"; empty -> null. */
export function parseNumber(text: string): number | null {
  const value = text.replace(/\s/g, '').replace(',', '.')
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Number -> text for an input, with the Russian decimal comma. */
export const inputNumber = (value: number | null | undefined) =>
  value === null || value === undefined ? '' : String(Number(value.toFixed(2))).replace('.', ',')

/** "понедельник, 14 сентября" -> "Понедельник, 14 сентября". */
export const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)
