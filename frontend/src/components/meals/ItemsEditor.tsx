import { useState } from 'react'
import { Plus, Tag, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { inputNumber, num, parseNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { MacroLine } from './MealBits'
import type { Confidence, GramsSource, MealItem, MealItemIn } from '@/types'

const VALUES = ['kcal', 'protein', 'fat', 'carbs'] as const
type Value = (typeof VALUES)[number]
type Values = Record<Value, string>
type Basis = 'portion' | 'per100'

/**
 * An item as typed: numbers stay text until saving, so "82," is not lost mid-typing.
 * The numbers are kept for the portion and per 100 g; the side the person typed (or the
 * label behind an estimate) is the truth, the other side follows it and the weight.
 */
export interface ItemDraft {
  key: string
  name: string
  product_id: number | null
  grams: string
  grams_source: GramsSource
  kcal: string
  protein: string
  fat: string
  carbs: string
  per100: Values
  basis: Basis
  confidence: Confidence | null
  note: string | null
}

let counter = 0
const nextKey = () => `item-${++counter}`
const blank = (): Values => ({ kcal: '', protein: '', fat: '', carbs: '' })
const round1 = (value: number) => inputNumber(Math.round(value * 10) / 10)
const weightOf = (item: ItemDraft) => {
  const grams = parseNumber(item.grams)
  return grams && grams > 0 ? grams : null
}

export const emptyItem = (): ItemDraft => ({
  key: nextKey(),
  name: '',
  product_id: null,
  grams: '',
  grams_source: 'stated',
  ...blank(),
  per100: blank(),
  basis: 'portion',
  confidence: null,
  note: null,
})

export function itemDraft(item: MealItem): ItemDraft {
  const per100 = blank()
  if (item.grams)
    for (const field of VALUES) per100[field] = round1((item[field] * 100) / item.grams)
  return {
    key: nextKey(),
    name: item.name,
    product_id: item.product_id,
    grams: inputNumber(item.grams),
    grams_source: item.grams_source,
    kcal: inputNumber(item.kcal),
    protein: inputNumber(item.protein),
    fat: inputNumber(item.fat),
    carbs: inputNumber(item.carbs),
    per100,
    // A changed weight rescales a known item: "it was 250 g, not 180".
    basis: item.grams ? 'per100' : 'portion',
    confidence: item.confidence,
    note: item.note,
  }
}

/** Fills the side that is not the truth from the side that is. */
function settle(item: ItemDraft): ItemDraft {
  const grams = weightOf(item)
  if (!grams) return item
  const next = { ...item, per100: { ...item.per100 } }
  for (const field of VALUES) {
    if (item.basis === 'per100') {
      const value = parseNumber(item.per100[field])
      next[field] = value === null ? '' : round1((value * grams) / 100)
    } else {
      const value = parseNumber(item[field])
      next.per100[field] = value === null ? '' : round1((value * 100) / grams)
    }
  }
  return next
}

const FIELDS: { field: Value; label: string; name: string; max: number; dot?: string }[] = [
  { field: 'kcal', label: 'Ккал', name: 'Калории', max: 10000 },
  { field: 'protein', label: 'Белки', name: 'Белки, г', max: 1000, dot: 'bg-macro-protein' },
  { field: 'fat', label: 'Жиры', name: 'Жиры, г', max: 1000, dot: 'bg-macro-fat' },
  { field: 'carbs', label: 'Углеводы', name: 'Углеводы, г', max: 2000, dot: 'bg-macro-carbs' },
]

/** -> items for the API, or the first problem as a message. */
export function toItems(drafts: ItemDraft[]): MealItemIn[] | string {
  if (!drafts.length) return 'Добавьте хотя бы один продукт'
  const items: MealItemIn[] = []
  for (const [index, draft] of drafts.entries()) {
    const where = draft.name.trim() || `Продукт ${index + 1}`
    if (!draft.name.trim()) return `Продукт ${index + 1}: напишите название`
    const grams = parseNumber(draft.grams)
    if (draft.grams.trim() && grams === null) return `${where}: проверьте вес`
    if (grams !== null && (grams <= 0 || grams > 5000)) return `${where}: вес от 1 до 5000 г`
    const values = {} as Record<Value, number | null>
    for (const { field, name, max } of FIELDS) {
      const value = parseNumber(draft[field])
      if (draft[field].trim() && value === null) return `${where}: проверьте поле «${name}»`
      if (value !== null && (value < 0 || value > max)) return `${where}: «${name}» вне допустимого`
      values[field] = value
    }
    if (values.kcal === null) return `${where}: укажите калории`
    items.push({
      name: draft.name.trim(),
      product_id: draft.product_id,
      grams,
      grams_source: draft.grams_source,
      kcal: values.kcal,
      protein: values.protein ?? 0,
      fat: values.fat ?? 0,
      carbs: values.carbs ?? 0,
      confidence: draft.confidence,
      note: draft.note,
    })
  }
  return items
}

/** What the form compares to see whether anything changed. */
export const comparableItems = (drafts: ItemDraft[]) =>
  JSON.stringify(
    drafts.map((draft) => [
      draft.name,
      draft.product_id,
      draft.grams,
      ...VALUES.map((f) => draft[f]),
    ]),
  )

export function draftTotals(drafts: ItemDraft[]) {
  const sum = (field: Value) =>
    drafts.reduce((total, draft) => total + (parseNumber(draft[field]) ?? 0), 0)
  return { kcal: sum('kcal'), protein: sum('protein'), fat: sum('fat'), carbs: sum('carbs') }
}

/** "120 ккал · Б 16,7 · Ж 5 · У 2,8" from text values. */
function valuesLine(values: Values) {
  const show = (text: string) => num(parseNumber(text) ?? 0, 1)
  return `${show(values.kcal)} ккал, Б ${show(values.protein)}, Ж ${show(values.fat)}, У ${show(values.carbs)}`
}

export function ItemsEditor({
  items,
  onChange,
}: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
}) {
  const [mode, setMode] = useState<Basis>('portion')
  const totals = draftTotals(items)
  const estimated = items.some((item) => item.grams_source === 'estimated')

  function update(key: string, change: (item: ItemDraft) => ItemDraft) {
    onChange(items.map((item) => (item.key === key ? change(item) : item)))
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="sr-only">Состав</legend>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="text-sm font-medium" aria-hidden="true">
          Состав
        </span>
        <div
          role="radiogroup"
          aria-label="Как вписывать КБЖУ"
          className="inline-flex rounded-[12px] bg-muted p-0.5"
        >
          {(
            [
              { value: 'portion', label: 'В порции' },
              { value: 'per100', label: 'На 100 г' },
            ] as const
          ).map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={mode === option.value}
              onClick={() => setMode(option.value)}
              className={cn(
                'min-h-9 rounded-[10px] px-3 text-[13px] font-medium transition-colors',
                mode === option.value
                  ? 'bg-foreground text-background shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {items.map((item, index) => {
        const title = item.name || `Продукт ${index + 1}`
        const grams = weightOf(item)
        const shown = mode === 'portion' ? item : item.per100
        return (
          <div key={item.key} className="rounded-[16px] border bg-card p-3">
            <div className="flex items-center gap-2">
              <Input
                value={item.name}
                onChange={(event) =>
                  update(item.key, (it) => ({ ...it, name: event.target.value }))
                }
                placeholder="Например, гречка"
                aria-label={`Продукт ${index + 1}: название`}
                maxLength={200}
                className="min-w-0 flex-1"
              />
              <label className="relative w-[88px] shrink-0">
                {item.grams_source === 'estimated' && item.grams && (
                  <span
                    className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  >
                    ~
                  </span>
                )}
                <Input
                  value={item.grams}
                  onChange={(event) =>
                    update(item.key, (it) =>
                      // A weight typed by the person is no longer a guess.
                      settle({ ...it, grams: event.target.value, grams_source: 'stated' }),
                    )
                  }
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="вес"
                  aria-label={`${title}: вес в граммах${
                    item.grams_source === 'estimated' ? ', оценка' : ''
                  }`}
                  className="pr-7 pl-5 text-right tabular"
                />
                <span
                  className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-sm text-muted-foreground"
                  aria-hidden="true"
                >
                  г
                </span>
              </label>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => onChange(items.filter((other) => other.key !== item.key))}
                disabled={items.length === 1}
                aria-label={`Убрать «${title}»`}
              >
                <Trash2 />
              </Button>
            </div>
            {item.product_id !== null && (
              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-accent-foreground">
                <Tag className="size-3.5" aria-hidden="true" />
                Мой продукт, числа с этикетки
              </p>
            )}
            <div className="mt-3 grid grid-cols-4 gap-1.5">
              {FIELDS.map(({ field, label, name, dot }) => (
                <label key={field} className="flex min-w-0 flex-col gap-1">
                  <span className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                    {dot && <span className={`macro-dot ${dot}`} aria-hidden="true" />}
                    {label}
                  </span>
                  <Input
                    value={shown[field]}
                    onChange={(event) => {
                      const text = event.target.value
                      update(item.key, (it) =>
                        settle(
                          mode === 'portion'
                            ? { ...it, [field]: text, basis: 'portion' }
                            : { ...it, per100: { ...it.per100, [field]: text }, basis: 'per100' },
                        ),
                      )
                    }}
                    disabled={mode === 'per100' && !grams}
                    inputMode="decimal"
                    autoComplete="off"
                    aria-label={`${title}: ${name} ${mode === 'portion' ? 'в порции' : 'на 100 г'}`}
                    className="px-2 text-center tabular"
                  />
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground tabular">
              {!grams
                ? mode === 'portion'
                  ? 'Впишите вес — посчитаю и на 100 г.'
                  : 'Впишите вес, чтобы считать на 100 г.'
                : mode === 'portion'
                  ? `На 100 г: ${valuesLine(item.per100)}`
                  : `В порции ${num(grams)} г: ${valuesLine(item)}`}
            </p>
          </div>
        )
      })}
      <Button
        type="button"
        variant="outline"
        className="self-start"
        onClick={() => onChange([...items, emptyItem()])}
        disabled={items.length >= 40}
      >
        <Plus />
        Добавить продукт
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-[14px] bg-muted px-3 py-2.5 text-sm">
        <span className="font-medium">Итого {num(totals.kcal)} ккал</span>
        <MacroLine value={totals} className="text-muted-foreground" />
      </div>
      {estimated && (
        <p className="text-xs text-muted-foreground">
          «~» — вес оценен на глаз. Впишите точный, если знаете: числа пересчитаются.
        </p>
      )}
    </fieldset>
  )
}
