import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ChartColumnBig, NotebookText, Plus, Scale, Send, Utensils } from 'lucide-react'
import { authApi, bodyApi, mealsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/shared/PageHeader'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { Skeleton } from '@/components/ui/skeleton'
import { CalorieRing, MacroTargets } from '@/components/home/DayProgress'
import { MealRow } from '@/components/meals/MealRow'
import { NewMealSheet } from '@/components/meals/NewMealSheet'
import { useMealParam } from '@/components/meals/MealSheet'
import { WeightSheet, weightChange } from '@/components/progress/WeightEditor'
import { TelegramLinkButton } from '@/components/shared/TelegramLinkButton'
import { addDays, dayLabel, formatDay, num, signed, timeOf, todayIn } from '@/lib/format'
import { botLink } from '@/lib/telegram'

export default function HomePage() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const { open } = useMealParam()
  const [adding, setAdding] = useState(false)
  const summary = useQuery({
    queryKey: keys.today,
    queryFn: ({ signal }) => mealsApi.today({ signal }),
  })
  const config = useQuery({
    queryKey: keys.authConfig,
    queryFn: ({ signal }) => authApi.config({ signal }),
    staleTime: Infinity,
  })

  const day = summary.data?.day ?? today
  return (
    <>
      <PageHeader title="Сегодня" meta={formatDay(day, 'EEEE, d MMMM')}>
        <Button
          onClick={() => setAdding(true)}
          className="max-sm:w-11 max-sm:px-0"
          aria-label="Добавить запись"
        >
          <Plus />
          <span className="max-sm:sr-only">Добавить</span>
        </Button>
        <span className="min-[900px]:hidden">
          <ThemeToggle />
        </span>
      </PageHeader>

      {!user.telegram_id && (
        <Card className="mb-4 border-primary/30">
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm">
              <p className="font-medium">Привяжите Telegram</p>
              <p className="text-muted-foreground">
                Фото еды, вес и вопросы удобнее всего присылать боту — записи появятся здесь.
              </p>
            </div>
            <TelegramLinkButton className="shrink-0" />
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-start">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Калории и БЖУ</CardTitle>
              {summary.data && summary.data.targets.kcal !== null && (
                <CardAction className="text-sm text-muted-foreground tabular">
                  цель {num(summary.data.targets.kcal)} ккал
                </CardAction>
              )}
            </CardHeader>
            <CardContent>
              {summary.isPending ? (
                <div className="flex flex-col items-center gap-6 sm:flex-row">
                  <Skeleton className="size-[168px] rounded-full" />
                  <BlockSkeleton rows={3} className="w-full flex-1" />
                </div>
              ) : summary.isError ? (
                <ErrorState error={summary.error} retry={() => summary.refetch()} />
              ) : (
                <div className="flex flex-col items-stretch gap-6 sm:flex-row sm:items-center">
                  <CalorieRing
                    eaten={summary.data.totals.kcal}
                    target={summary.data.targets.kcal}
                  />
                  <div className="flex min-w-0 flex-1 flex-col gap-4">
                    <MacroTargets totals={summary.data.totals} targets={summary.data.targets} />
                    {summary.data.targets.kcal === null && (
                      <p className="text-sm text-muted-foreground">
                        Цель по калориям не задана.{' '}
                        <Link
                          to="/profile"
                          className="font-medium text-primary underline-offset-4 hover:underline"
                        >
                          Рассчитать в профиле
                        </Link>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="gap-2 pb-2">
            <CardHeader>
              <CardTitle>Приемы пищи</CardTitle>
              {summary.data && summary.data.drafts > 0 && (
                <CardAction className="text-sm text-warning">
                  {summary.data.drafts === 1 ? '1 черновик' : `черновиков: ${summary.data.drafts}`}
                </CardAction>
              )}
            </CardHeader>
            {summary.isPending ? (
              <CardContent className="pb-4">
                <BlockSkeleton rows={3} />
              </CardContent>
            ) : summary.data?.meals.length ? (
              <div className="row-list">
                {summary.data.meals.map((meal) => (
                  <MealRow key={meal.id} meal={meal} onOpen={open} />
                ))}
              </div>
            ) : summary.data ? (
              <EmptyState
                icon={Utensils}
                title="Сегодня пока пусто"
                description="Пришлите боту фото еды или напишите, что съели, — запись появится здесь."
              >
                {config.data && (
                  <Button asChild variant="outline">
                    <a
                      href={botLink(config.data.bot_username)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Send />
                      Открыть бота
                    </a>
                  </Button>
                )}
                <Button variant="ghost" onClick={() => setAdding(true)}>
                  <Plus />
                  Добавить вручную
                </Button>
              </EmptyState>
            ) : null}
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <WeightCard today={today} />
          <nav aria-label="Быстрые ссылки" className="grid grid-cols-2 gap-3">
            <QuickLink to="/diary" icon={NotebookText} label="Дневник" hint="Все записи" />
            <QuickLink
              to="/analytics"
              icon={ChartColumnBig}
              label="Аналитика"
              hint="Графики и отчет"
            />
          </nav>
        </div>
      </div>

      <NewMealSheet open={adding} onOpenChange={setAdding} />
    </>
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
            <div>
              <p className="text-[32px] leading-none font-semibold tracking-tight">
                {num(latest.weight_kg, 1)}{' '}
                <span className="text-lg font-normal text-muted-foreground">кг</span>
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                {dayLabel(latest.measured_on, today)}, {timeOf(latest.measured_at)}
              </p>
            </div>
            {change !== null && (
              <div className="text-right">
                <p className="text-lg font-semibold tabular">{signed(change)} кг</p>
                <p className="text-xs text-muted-foreground">за 7 дней</p>
              </div>
            )}
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
            className="mt-4 inline-flex min-h-11 items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            История и замеры
            <ArrowRight className="size-4" />
          </Link>
        )}
      </CardContent>
      <WeightSheet open={adding} onOpenChange={setAdding} />
    </Card>
  )
}

function QuickLink({
  to,
  icon: Icon,
  label,
  hint,
}: {
  to: string
  icon: typeof NotebookText
  label: string
  hint: string
}) {
  return (
    <Link
      to={to}
      className="group flex flex-col gap-3 rounded-[20px] border bg-card p-4 shadow-[var(--card-shadow)] transition-colors hover:border-primary/40"
    >
      <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-foreground">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <span>
        <span className="flex items-center gap-1 font-medium">
          {label}
          <ArrowRight
            className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
        <span className="text-sm text-muted-foreground">{hint}</span>
      </span>
    </Link>
  )
}
