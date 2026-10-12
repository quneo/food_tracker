import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Scale, Send, Utensils } from 'lucide-react'
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
import { cn } from '@/lib/utils'
import breakfast from '@/assets/breakfast.webp'

export default function HomePage() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const { open } = useMealParam()
  const [adding, setAdding] = useState(false)
  const summary = useQuery({
    queryKey: keys.today,
    queryFn: ({ signal }) => mealsApi.today({ signal }),
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

      {/* Phones: the first thing on the page; wide screens: in the side column. */}
      {!user.telegram_id && <LinkTelegramCard className="mb-4 min-[1180px]:hidden" />}

      <div className="page-grid">
        <div className="flex min-w-0 flex-col gap-4">
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
                  <Skeleton className="size-[188px] rounded-full" />
                  <BlockSkeleton rows={3} className="w-full flex-1" />
                </div>
              ) : summary.isError ? (
                <ErrorState error={summary.error} retry={() => summary.refetch()} />
              ) : (
                <div className="flex flex-col items-stretch gap-7 sm:flex-row sm:items-center">
                  <CalorieRing
                    eaten={summary.data.totals.kcal}
                    target={summary.data.targets.kcal}
                  />
                  <div className="flex min-w-0 flex-1 flex-col gap-4">
                    <p className="text-[15px]">
                      Съедено{' '}
                      <span className="serif-number text-lg">{num(summary.data.totals.kcal)}</span>{' '}
                      ккал
                      {summary.data.drafts > 0 && (
                        <span className="text-muted-foreground">, черновики не в счет</span>
                      )}
                    </p>
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
                {/* The latest first, like the diary. */}
                {[...summary.data.meals]
                  .sort((a, b) => (a.eaten_at < b.eaten_at ? 1 : -1))
                  .map((meal) => (
                    <MealRow key={meal.id} meal={meal} onOpen={open} />
                  ))}
              </div>
            ) : summary.data ? (
              <EmptyState
                icon={Utensils}
                title="Сегодня пока пусто"
                description="Пришлите боту фото тарелки или напишите, что съели, и запись появится здесь."
              >
                <Button variant="ghost" onClick={() => setAdding(true)}>
                  <Plus />
                  Добавить вручную
                </Button>
              </EmptyState>
            ) : null}
          </Card>
        </div>

        <aside className="page-side" aria-label="Вес и бот">
          {!user.telegram_id && <LinkTelegramCard className="hidden min-[1180px]:flex" />}
          <WeightCard today={today} />
          {user.telegram_id && <BotCard />}
        </aside>
      </div>

      <NewMealSheet open={adding} onOpenChange={setAdding} />
    </>
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
          Еду, вес и вопросы удобнее всего присылать боту. Записи сразу появятся здесь.
        </p>
        <TelegramLinkButton className="self-start" />
      </CardContent>
    </Card>
  )
}

/** The bot is where things get written down; this card says how, with the house drawing. */
function BotCard() {
  const config = useQuery({
    queryKey: keys.authConfig,
    queryFn: ({ signal }) => authApi.config({ signal }),
    staleTime: Infinity,
  })
  return (
    <Card className="overflow-hidden pt-0">
      <img
        src={breakfast}
        alt=""
        className="mx-auto -mb-2 w-[78%] max-w-[260px] pt-4 select-none"
        draggable={false}
      />
      <CardContent className="flex flex-col gap-3">
        <p className="section-title">Записывайте в Telegram</p>
        <p className="text-sm text-muted-foreground">
          Фото тарелки или пара слов: «гречка с курицей, 300 г». Вес — просто числом.
        </p>
        {config.data && (
          <Button asChild variant="outline" className="self-start">
            <a href={botLink(config.data.bot_username)} target="_blank" rel="noopener noreferrer">
              <Send />
              Открыть @{config.data.bot_username}
            </a>
          </Button>
        )}
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
              <p className="hero-number text-[40px]">
                {num(latest.weight_kg, 1)}{' '}
                <span className="font-sans text-lg font-normal text-muted-foreground">кг</span>
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                {dayLabel(latest.measured_on, today)}, {timeOf(latest.measured_at)}
              </p>
            </div>
            {change !== null && (
              <div className="text-right">
                <p className="serif-number text-lg">{signed(change)} кг</p>
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
            className="mt-4 inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            История и замеры
          </Link>
        )}
      </CardContent>
      <WeightSheet open={adding} onOpenChange={setAdding} />
    </Card>
  )
}
