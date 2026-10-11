import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { inputNumber, num, parseNumber } from '@/lib/format'
import { MacroLine } from './MealBits'
import type { Confidence, GramsSource, MealItem, MealItemIn } from '@/types'

/** An item as typed: numbers stay text until saving, so "82," is not lost mid-typing. */
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
  confidence: Confidence | null
  note: string | null
}

let counter = 0
const nextKey = () => `item-${++counter}`

export const emptyItem = (): ItemDraft => ({
  key: nextKey(),
  name: '',
  product_id: null,
  grams: '',
  grams_source: 'stated',
  kcal: '',
  protein: '',
  fat: '',
  carbs: '',
  confidence: null,
  note: null,
})

export const itemDraft = (item: MealItem): ItemDraft => ({
  key: nextKey(),
  name: item.name,
  product_id: item.product_id,
  grams: inputNumber(item.grams),
  grams_source: item.grams_source,
  kcal: inputNumber(item.kcal),
  protein: inputNumber(item.protein),
  fat: inputNumber(item.fat),
  carbs: inputNumber(item.carbs),
  confidence: item.confidence,
  note: item.note,
})

const NUMBERS = [
  { field: 'grams', label: 'Вес, г', name: 'Вес в граммах', max: 5000 },
  { field: 'kcal', label: 'ккал', name: 'Калории', max: 10000 },
  { field: 'protein', label: 'Б, г', name: 'Белки, г', max: 1000 },
  { field: 'fat', label: 'Ж, г', name: 'Жиры, г', max: 1000 },
  { field: 'carbs', label: 'У, г', name: 'Углеводы, г', max: 2000 },
] as const

/** -> items for the API, or the first problem as a message. */
export function toItems(drafts: ItemDraft[]): MealItemIn[] | string {
  if (!drafts.length) return 'Добавьте хотя бы один продукт'
  const items: MealItemIn[] = []
  for (const [index, draft] of drafts.entries()) {
    const where = draft.name.trim() || `Продукт ${index + 1}`
    if (!draft.name.trim()) return `Продукт ${index + 1}: напишите название`
    const values: Record<string, number | null> = {}
    for (const { field, name, max } of NUMBERS) {
      const value = parseNumber(draft[field])
      if (draft[field].trim() && value === null) return `${where}: проверьте поле «${name}»`
      if (value !== null && (value < 0 || value > max)) return `${where}: «${name}» вне допустимого`
      values[field] = value
    }
    if (values.kcal === null) return `${where}: укажите калории`
    if (values.grams === 0) return `${where}: вес больше нуля или пусто`
    items.push({
      name: draft.name.trim(),
      product_id: draft.product_id,
      grams: values.grams,
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

export function draftTotals(drafts: ItemDraft[]) {
  const sum = (field: 'kcal' | 'protein' | 'fat' | 'carbs') =>
    drafts.reduce((total, draft) => total + (parseNumber(draft[field]) ?? 0), 0)
  return { kcal: sum('kcal'), protein: sum('protein'), fat: sum('fat'), carbs: sum('carbs') }
}

export function ItemsEditor({
  items,
  onChange,
}: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
}) {
  const totals = draftTotals(items)
  const estimated = items.some((item) => item.grams_source === 'estimated')

  function update(key: string, patch: Partial<ItemDraft>) {
    onChange(items.map((item) => (item.key === key ? { ...item, ...patch } : item)))
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-sm font-medium">Состав</legend>
      {items.map((item, index) => (
        <div key={item.key} className="rounded-[14px] border bg-card p-3">
          <div className="flex items-center gap-2">
            <Input
              value={item.name}
              onChange={(event) => update(item.key, { name: event.target.value })}
              placeholder="Например, гречка"
              aria-label={`Продукт ${index + 1}: название`}
              maxLength={200}
              className="flex-1"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => onChange(items.filter((other) => other.key !== item.key))}
              disabled={items.length === 1}
              aria-label={`Убрать «${item.name || `продукт ${index + 1}`}»`}
            >
              <Trash2 />
            </Button>
          </div>
          <div className="mt-2 grid grid-cols-5 gap-1.5">
            {NUMBERS.map(({ field, label, name }) => (
              <label key={field} className="flex min-w-0 flex-col gap-1">
                <span className="truncate text-xs text-muted-foreground">{label}</span>
                <span className="relative">
                  {field === 'grams' && item.grams_source === 'estimated' && item.grams && (
                    <span
                      className="pointer-events-none absolute top-1/2 left-1.5 -translate-y-1/2 text-muted-foreground"
                      aria-hidden="true"
                    >
                      ~
                    </span>
                  )}
                  <Input
                    value={item[field]}
                    onChange={(event) =>
                      update(item.key, {
                        [field]: event.target.value,
                        // A weight typed by the person is no longer a guess.
                        ...(field === 'grams' ? { grams_source: 'stated' as const } : {}),
                      })
                    }
                    inputMode="decimal"
                    autoComplete="off"
                    aria-label={`${item.name || `Продукт ${index + 1}`}: ${name}${
                      field === 'grams' && item.grams_source === 'estimated' ? ', оценка' : ''
                    }`}
                    className="px-2 text-center tabular"
                  />
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}
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
          «~» — вес оценен на глаз. Впишите точный, если знаете.
        </p>
      )}
    </fieldset>
  )
}
