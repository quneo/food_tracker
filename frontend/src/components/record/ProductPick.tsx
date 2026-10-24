import { useDeferredValue, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, PackageOpen, Search } from 'lucide-react'
import { toast } from 'sonner'
import { mealsApi, productsApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { MacroLine } from '@/components/meals/MealBits'
import { Photo } from '@/components/shared/Photo'
import { inputNumber, num, parseNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Product } from '@/types'

/** A saved product and how much of it: the label gives the numbers, no assistant needed. */
export function ProductPick({ onDone }: { onDone: () => void }) {
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<Product | null>(null)
  const search = useDeferredValue(query.trim())
  const products = useQuery({
    queryKey: [...keys.products, search],
    queryFn: ({ signal }) => productsApi.list(search || null, { signal }),
  })
  if (chosen) return <Amount product={chosen} onBack={() => setChosen(null)} onDone={onDone} />
  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Найти продукт"
          className="pl-10"
          aria-label="Найти продукт"
        />
      </div>
      {products.isPending ? (
        <BlockSkeleton rows={3} />
      ) : products.isError ? (
        <ErrorState error={products.error} retry={() => products.refetch()} />
      ) : products.data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
          <PackageOpen className="size-7" aria-hidden="true" />
          {search
            ? 'Ничего не нашлось'
            : 'Своих продуктов пока нет. Сохраните их в «Дневник → Мои продукты» или пришлите боту фото этикетки.'}
        </div>
      ) : (
        <ul className="row-list -mx-1 flex flex-col">
          {products.data.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                className="flex w-full items-center gap-3 rounded-[14px] px-1 py-2.5 text-left transition-colors hover:bg-muted"
                onClick={() => setChosen(product)}
              >
                {product.photos[0] ? (
                  <Photo id={product.photos[0].id} alt="" className="thumb" />
                ) : (
                  <span className="thumb grid place-items-center text-muted-foreground">
                    <PackageOpen className="size-5" aria-hidden="true" />
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 font-medium leading-snug">{product.name}</span>
                  <span className="text-[13px] text-muted-foreground tabular">
                    {num(product.kcal)} ккал на 100 г
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Amount({
  product,
  onBack,
  onDone,
}: {
  product: Product
  onBack: () => void
  onDone: () => void
}) {
  const client = useQueryClient()
  const start = product.portion_grams ?? 100
  const [text, setText] = useState(inputNumber(start))
  const grams = parseNumber(text)
  const valid = grams !== null && grams > 0 && grams <= 5000
  const share = valid ? grams / 100 : 0
  const totals = {
    kcal: product.kcal * share,
    protein: product.protein * share,
    fat: product.fat * share,
    carbs: product.carbs * share,
  }
  const presets = [
    product.portion_grams && {
      label: product.portion_name ? `${product.portion_name}` : 'Порция',
      grams: product.portion_grams,
    },
    product.package_grams && { label: 'Упаковка', grams: product.package_grams },
    { label: '100 г', grams: 100 },
  ].filter(Boolean) as { label: string; grams: number }[]

  const save = useMutation({
    mutationFn: () =>
      mealsApi.create({
        title: product.name.slice(0, 200),
        meal_type: null,
        eaten_at: null,
        note: null,
        items: [
          {
            name: product.name.slice(0, 200),
            product_id: product.id,
            grams: grams!,
            grams_source: 'stated',
            kcal: Math.round(totals.kcal * 10) / 10,
            protein: Math.round(totals.protein * 10) / 10,
            fat: Math.round(totals.fat * 10) / 10,
            carbs: Math.round(totals.carbs * 10) / 10,
          },
        ],
      }),
    onSuccess: () => {
      toast.success('Записано в дневник')
      onDone()
      return invalidateMeals(client)
    },
  })

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid) save.mutate()
      }}
    >
      <button
        type="button"
        onClick={onBack}
        className="-ml-1 inline-flex min-h-9 items-center gap-1 self-start text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        Все продукты
      </button>
      <p className="font-semibold leading-snug">{product.name}</p>
      <div className="flex flex-col gap-2">
        <label htmlFor="product-grams" className="text-sm font-medium">
          Сколько, граммов
        </label>
        <Input
          id="product-grams"
          inputMode="decimal"
          value={text}
          onChange={(event) => setText(event.target.value)}
          aria-invalid={!valid}
        />
        <div className="chips">
          {presets.map((preset) => (
            <button
              key={preset.label}
              type="button"
              className="chip"
              aria-pressed={grams === preset.grams}
              onClick={() => setText(inputNumber(preset.grams))}
            >
              {preset.label}
              {preset.label !== '100 г' && (
                <span className="text-xs opacity-70">{num(preset.grams)} г</span>
              )}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-end justify-between gap-3 rounded-[18px] bg-muted p-4">
        <MacroLine value={totals} className="text-[13px] text-muted-foreground" />
        <span className={cn('serif-number text-2xl leading-none', !valid && 'opacity-40')}>
          {num(totals.kcal)} <span className="font-sans text-xs font-normal">ккал</span>
        </span>
      </div>
      <Button type="submit" size="lg" className="min-h-12" disabled={!valid || save.isPending}>
        <Check />
        Записать
      </Button>
    </form>
  )
}
