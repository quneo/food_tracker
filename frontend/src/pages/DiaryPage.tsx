import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useInfiniteQuery } from '@tanstack/react-query'
import { ChevronDown, NotebookText, Plus, X } from 'lucide-react'
import { mealsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/shared/PageHeader'
import { DateRangePicker } from '@/components/shared/DateRangePicker'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { MealCard } from '@/components/meals/MealCard'
import { MacroLine } from '@/components/meals/MealBits'
import { NewMealSheet } from '@/components/meals/NewMealSheet'
import { useMealParam } from '@/components/meals/MealSheet'
import { ProductsView } from '@/components/products/ProductsView'
import { MEAL_TYPES } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { addDays, dayLabel, num, rangeLabel, todayIn } from '@/lib/format'
import type { Meal, MealStatus, MealType } from '@/types'

const DAY = /^\d{4}-\d{2}-\d{2}$/

interface Page {
  start: string
  end: string
  meals: Meal[]
}

export default function DiaryPage() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const { open } = useMealParam()
  const [params, setParams] = useSearchParams()
  const [adding, setAdding] = useState(false)

  const rawFrom = params.get('from') ?? ''
  const rawTo = params.get('to') ?? ''
  const from = DAY.test(rawFrom) ? rawFrom : null
  const to = from ? (DAY.test(rawTo) && rawTo >= from ? rawTo : today) : null
  const type = MEAL_TYPES.some((item) => item.value === params.get('type'))
    ? (params.get('type') as MealType)
    : null
  const status: MealStatus | null = params.get('status') === 'draft' ? 'draft' : null
  const products = params.get('tab') === 'products'
  // Without a chosen period the feed goes back week by week, up to a year before sign-up.
  const floor = from ?? addDays(user.created_at.slice(0, 10), -365)

  function update(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(values))
      if (value) next.set(key, value)
      else next.delete(key)
    setParams(next, { replace: true })
  }

  const feed = useInfiniteQuery({
    queryKey: [...keys.meals, 'feed', { from, to, type, status, today }],
    initialPageParam: to ?? today,
    queryFn: async ({ pageParam, signal }): Promise<Page> => {
      const end = pageParam
      const weekStart = addDays(end, -6)
      const start = from && weekStart < from ? from : weekStart
      const meals = await mealsApi.list(
        { from: start, to: end, meal_type: type, status },
        { signal },
      )
      return { start, end, meals }
    },
    getNextPageParam: (last) => {
      const next = addDays(last.start, -1)
      return next < floor ? undefined : next
    },
  })

  const pages = feed.data?.pages ?? []
  const anyMeals = pages.some((page) => page.meals.length > 0)
  const filtered = Boolean(from || type || status)

  return (
    <>
      <PageHeader title="Дневник">
        {!products && (
          <Button
            onClick={() => setAdding(true)}
            className="max-sm:w-11 max-sm:px-0"
            aria-label="Добавить запись"
          >
            <Plus />
            <span className="max-sm:sr-only">Добавить</span>
          </Button>
        )}
      </PageHeader>

      <div
        className="mb-4 inline-flex rounded-[16px] glass p-1"
        role="tablist"
        aria-label="Раздел дневника"
      >
        {[
          { value: null, label: 'Лента' },
          { value: 'products', label: 'Мои продукты' },
        ].map((tab) => (
          <button
            key={tab.label}
            type="button"
            role="tab"
            aria-selected={(tab.value === 'products') === products}
            onClick={() => update({ tab: tab.value })}
            className={cn(
              'min-h-10 rounded-[12px] px-4 text-sm font-medium transition-colors',
              (tab.value === 'products') === products
                ? 'bg-card text-foreground shadow-sm dark:bg-white/10'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {products ? (
        <ProductsView />
      ) : (
        <div className="page-grid">
          <div className="chat-column">
            {feed.isPending ? (
              <BlockSkeleton rows={4} />
            ) : feed.isError ? (
              <ErrorState error={feed.error} retry={() => feed.refetch()} />
            ) : (
              <>
                {!anyMeals && !feed.hasNextPage && (
                  <EmptyState
                    icon={NotebookText}
                    title={filtered ? 'Ничего не нашлось' : 'Записей пока нет'}
                    description={
                      filtered
                        ? 'Попробуйте другой период или уберите фильтры.'
                        : 'Пришлите боту фото или описание еды, либо добавьте запись вручную.'
                    }
                  />
                )}
                {pages.map((page) => (
                  <PageDays key={page.end} page={page} today={today} onOpen={open} />
                ))}
                {feed.hasNextPage && (
                  <Button
                    variant="outline"
                    className="self-center rounded-full"
                    onClick={() => feed.fetchNextPage()}
                    disabled={feed.isFetchingNextPage}
                  >
                    <ChevronDown />
                    {feed.isFetchingNextPage
                      ? 'Загружаем…'
                      : `Показать раньше: ${rangeLabel(
                          addDays(pages[pages.length - 1].start, -7) < floor
                            ? floor
                            : addDays(pages[pages.length - 1].start, -7),
                          addDays(pages[pages.length - 1].start, -1),
                        )}`}
                  </Button>
                )}
              </>
            )}
          </div>
          <aside className="page-side diary-side" aria-label="Фильтры">
            <div
              className="glass flex flex-col gap-3 rounded-[24px] p-4"
              role="group"
              aria-label="Фильтры"
            >
              <p className="section-title hidden min-[1180px]:block">Показать</p>
              <div className="flex flex-wrap items-center gap-2">
                <DateRangePicker
                  from={from ?? undefined}
                  to={to ?? undefined}
                  today={today}
                  onChange={(start, end) => update({ from: start, to: end })}
                  label={from && to ? rangeLabel(from, to) : 'Все даты'}
                  className="rounded-full"
                />
                {from && (
                  <Button
                    variant="ghost"
                    className="rounded-full text-muted-foreground"
                    onClick={() => update({ from: null, to: null })}
                  >
                    <X />
                    Сбросить период
                  </Button>
                )}
              </div>
              <div className="chips">
                <button
                  type="button"
                  className="chip"
                  aria-pressed={!type}
                  onClick={() => update({ type: null })}
                >
                  Все
                </button>
                {MEAL_TYPES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className="chip"
                    aria-pressed={type === item.value}
                    onClick={() => update({ type: type === item.value ? null : item.value })}
                  >
                    {item.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="chip"
                  aria-pressed={status === 'draft'}
                  onClick={() => update({ status: status ? null : 'draft' })}
                >
                  Черновики
                </button>
              </div>
            </div>
          </aside>
        </div>
      )}

      <NewMealSheet open={adding} onOpenChange={setAdding} />
    </>
  )
}

function PageDays({
  page,
  today,
  onOpen,
}: {
  page: Page
  today: string
  onOpen: (id: number) => void
}) {
  const days = useMemo(() => {
    const groups = new Map<string, Meal[]>()
    for (const meal of page.meals) {
      const list = groups.get(meal.eaten_on) ?? []
      list.push(meal)
      groups.set(meal.eaten_on, list)
    }
    return [...groups.entries()].sort(([a], [b]) => (a < b ? 1 : -1))
  }, [page.meals])

  if (!days.length)
    return <p className="service-line">{rangeLabel(page.start, page.end)}: записей нет</p>
  return (
    <>
      {days.map(([day, meals]) => (
        <DaySection key={day} day={day} meals={meals} today={today} onOpen={onOpen} />
      ))}
    </>
  )
}

function DaySection({
  day,
  meals,
  today,
  onOpen,
}: {
  day: string
  meals: Meal[]
  today: string
  onOpen: (id: number) => void
}) {
  const confirmed = meals.filter((meal) => meal.status === 'confirmed')
  const totals = {
    kcal: confirmed.reduce((sum, meal) => sum + meal.kcal, 0),
    protein: confirmed.reduce((sum, meal) => sum + meal.protein, 0),
    fat: confirmed.reduce((sum, meal) => sum + meal.fat, 0),
    carbs: confirmed.reduce((sum, meal) => sum + meal.carbs, 0),
  }
  const drafts = meals.length - confirmed.length
  // Days go newest first; within a day meals read in the order they were eaten.
  const ordered = [...meals].sort((a, b) => (a.eaten_at < b.eaten_at ? -1 : 1))
  return (
    <section aria-labelledby={`day-${day}`} className="flex flex-col gap-2.5">
      <h2 id={`day-${day}`} className="date-pill">
        {dayLabel(day, today)}
      </h2>
      {ordered.map((meal) => (
        <MealCard key={meal.id} meal={meal} onOpen={onOpen} />
      ))}
      <p className="service-line flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <span>
          Итог дня{' '}
          <span className="font-medium text-foreground tabular">{num(totals.kcal)} ккал</span>
        </span>
        <MacroLine value={totals} />
        {drafts > 0 && <span className="text-warning">черновики не в счет: {drafts}</span>}
      </p>
    </section>
  )
}
