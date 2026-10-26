import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Scale, ScanLine, Sparkles, Utensils } from 'lucide-react'
import { analyticsApi, bodyApi, mealsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/shared/PageHeader'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { Skeleton } from '@/components/ui/skeleton'
import { DayHero } from '@/components/home/DayHero'
import { Sparkline } from '@/components/home/Sparkline'
import { WeekBars } from '@/components/home/WeekBars'
import { WeekStrip, weekStart } from '@/components/home/WeekStrip'
import { MealRow } from '@/components/meals/MealRow'
import { NotesCard } from '@/components/notes/NotesCard'
import { useMealParam } from '@/components/meals/MealSheet'
import { useRecordParam } from '@/components/record/RecordSheet'
import { WeightSheet, weightChange } from '@/components/progress/WeightEditor'
import { TelegramLinkButton } from '@/components/shared/TelegramLinkButton'
import {
  addDays,
  cap,
  dayLabel,
  formatDay,
  nowIn,
  num,
  signed,
  timeOf,
  todayIn,
} from '@/lib/format'
import { cn } from '@/lib/utils'
import type { DaySummary, Meal } from '@/types'

const DAY = /^\d{4}-\d{2}-\d{2}$/

function greeting(timeZone: string, name: string) {
  const hour = Number(nowIn(timeZone).slice(11, 13))
  const part =
    hour < 5
      ? 'Доброй ночи'
      : hour < 12
        ? 'Доброе утро'
        : hour < 18
          ? 'Добрый день'
          : 'Добрый вечер'
  const first = name.trim().split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

export default function HomePage() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const { open } = useMealParam()
  const record = useRecordParam()
  const [params, setParams] = useSearchParams()
  const raw = params.get('day') ?? ''
  const day = DAY.test(raw) && raw <= today ? raw : today
  const [start, setStart] = useState(() => weekStart(day))
  const isToday = day === today

  const select = (value: string) => {
    const next = new URLSearchParams(params)
    if (value === today) next.delete('day')
    else next.set('day', value)
    setParams(next, { replace: true })
    setStart(weekStart(value))
  }

  const summary = useQuery({
    queryKey: isToday ? keys.today : keys.day(day),
    queryFn: ({ signal }) => (isToday ? mealsApi.today({ signal }) : mealsApi.day(day, { signal })),
  })
  const week = useQuery({
    queryKey: [...keys.daily, 'week', start],
    queryFn: ({ signal }) => analyticsApi.daily(start, addDays(start, 6), { signal }),
  })
  const target = summary.data?.targets.kcal ?? null

  return (
    <>
      <PageHeader
        title={greeting(user.timezone, user.name)}
        meta={cap(formatDay(today, 'EEEE, d MMMM'))}
      >
        <span className="min-[900px]:hidden">
          <ThemeToggle />
        </span>
      </PageHeader>

      {!user.telegram_id && <LinkTelegramCard className="mb-4 min-[1180px]:hidden" />}

      <div className="page-grid">
        <div className="flex min-w-0 flex-col gap-4">
          <WeekStrip
            start={start}
            today={today}
            selected={day}
            rows={week.data}
            target={target}
            onSelect={select}
            onWeek={setStart}
          />
          {summary.isPending ? (
            <Skeleton className="h-[260px] w-full rounded-[28px]" />
          ) : summary.isError ? (
            <ErrorState error={summary.error} retry={() => summary.refetch()} />
          ) : (
            <DayHero summary={summary.data} isToday={isToday} />
          )}
          {isToday && <NotesCard />}
          {summary.data && (
            <CoachNote meals={summary.data.meals} onOpen={open} className="min-[1180px]:hidden" />
          )}
          <MealsCard
            summary={summary.data}
            pending={summary.isPending}
            day={isToday ? null : dayLabel(day, today)}
            onOpen={open}
            onRecord={() => record.open()}
          />
        </div>

        <aside className="page-side" aria-label="Неделя и вес">
          {!user.telegram_id && <LinkTelegramCard className="hidden min-[1180px]:flex" />}
          {summary.data && (
            <CoachNote meals={summary.data.meals} onOpen={open} className="max-[1179px]:hidden" />
          )}
          <WeekBars
            start={start}
            today={today}
            selected={day}
            rows={week.data}
            target={target}
            onSelect={select}
          />
          <WeightCard today={today} />
        </aside>
      </div>
    </>
  )
}

function MealsCard({
  summary,
  pending,
  day,
  onOpen,
  onRecord,
}: {
  summary: DaySummary | undefined
  pending: boolean
  day: string | null
  onOpen: (id: number) => void
  onRecord: () => void
}) {
  return (
    <Card className="gap-2 pb-2">
      <CardHeader>
        <CardTitle>Приемы пищи</CardTitle>
        <CardAction className="flex items-center gap-3 text-sm">
          {summary && summary.drafts > 0 && (
            <span className="text-warning">
              {summary.drafts === 1 ? '1 черновик' : `черновиков: ${summary.drafts}`}
            </span>
          )}
          {day && <span className="text-muted-foreground">{day}</span>}
        </CardAction>
      </CardHeader>
      {pending ? (
        <CardContent className="pb-4">
          <BlockSkeleton rows={3} />
        </CardContent>
      ) : summary?.meals.length ? (
        <div className="row-list">
          {/* The latest first, like the diary. */}
          {[...summary.meals]
            .sort((a, b) => (a.eaten_at < b.eaten_at ? 1 : -1))
            .map((meal) => (
              <MealRow key={meal.id} meal={meal} onOpen={onOpen} />
            ))}
        </div>
      ) : summary ? (
        <EmptyState
          icon={Utensils}
          title="Записей нет"
          description="Сфотографируйте тарелку или опишите словами, ассистент посчитает."
        >
          <Button onClick={onRecord}>
            <ScanLine />
            Записать
          </Button>
        </EmptyState>
      ) : null}
    </Card>
  )
}

/** The assistant's latest note on the day's food. */
function CoachNote({
  meals,
  onOpen,
  className,
}: {
  meals: Meal[]
  onOpen: (id: number) => void
  className?: string
}) {
  const latest = [...meals]
    .filter((meal) => meal.ai_comment)
    .sort((a, b) => (a.eaten_at < b.eaten_at ? 1 : -1))[0]
  if (!latest) return null
  return (
    <section
      className={cn('glass flex flex-col gap-2 rounded-[24px] p-5', className)}
      aria-label="Совет ассистента"
    >
      <p className="flex items-center gap-2 text-sm font-medium text-accent-foreground">
        <span className="grid size-7 place-items-center rounded-full bg-lime text-lime-ink">
          <Sparkles className="size-4" aria-hidden="true" />
        </span>
        Совет ассистента
      </p>
      <p className="text-[15px] leading-relaxed">{latest.ai_comment}</p>
      <button
        type="button"
        onClick={() => onOpen(latest.id)}
        className="self-start text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        К записи «{latest.title}», {timeOf(latest.eaten_at)}
      </button>
    </section>
  )
}

function LinkTelegramCard({ className }: { className?: string }) {
  return (
    <Card className={cn('border-primary/30', className)}>
      <CardHeader>
        <CardTitle>Привяжите Telegram</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          В боте удобно присылать еду и вопросы ассистенту. Записи сразу появятся здесь.
        </p>
        <TelegramLinkButton className="self-start" />
      </CardContent>
    </Card>
  )
}

function WeightCard({ today }: { today: string }) {
  const [adding, setAdding] = useState(false)
  const weights = useQuery({
    queryKey: [...keys.weights, 'recent', today],
    queryFn: ({ signal }) => bodyApi.weights({ start: addDays(today, -60) }, { signal }),
  })
  const latest = weights.data?.[0]
  const change = weights.data ? weightChange(weights.data) : null
  const line = (weights.data ?? [])
    .filter((entry) => entry.measured_on >= addDays(today, -30))
    .map((entry) => entry.weight_kg)
    .reverse()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Вес</CardTitle>
        <CardAction>
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            <Plus />
            Записать
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {weights.isPending ? (
          <Skeleton className="h-16 w-full rounded-[14px]" />
        ) : weights.isError ? (
          <ErrorState error={weights.error} retry={() => weights.refetch()} />
        ) : latest ? (
          <div className="flex items-end justify-between gap-4">
            <div className="min-w-0">
              <p className="hero-number text-[40px]">
                {num(latest.weight_kg, 1)}{' '}
                <span className="font-sans text-lg font-normal text-muted-foreground">кг</span>
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                {dayLabel(latest.measured_on, today)}, {timeOf(latest.measured_at)}
              </p>
              {change !== null && (
                <p className="text-sm text-muted-foreground">
                  <span className="font-medium text-foreground tabular">{signed(change)} кг</span>{' '}
                  за неделю
                </p>
              )}
            </div>
            <Sparkline values={line} label="Вес за последние 30 дней" />
          </div>
        ) : (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Scale className="size-5 shrink-0" aria-hidden="true" />
            Взвешиваний пока нет. Пришлите вес боту или запишите здесь.
          </div>
        )}
        {latest && (
          <Link
            to="/progress?tab=body"
            className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            История и замеры
          </Link>
        )}
      </CardContent>
      <WeightSheet open={adding} onOpenChange={setAdding} />
    </Card>
  )
}
