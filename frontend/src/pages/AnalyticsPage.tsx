import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChartColumnBig, Ruler, Scale } from 'lucide-react'
import { analyticsApi, bodyApi, profileApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { DateRangePicker } from '@/components/shared/DateRangePicker'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { CaloriesChart, MacrosChart } from '@/components/analytics/NutritionCharts'
import { TrendLine, type TrendPoint } from '@/components/analytics/TrendLine'
import { ReportCard } from '@/components/analytics/ReportCard'
import { DaySheet } from '@/components/analytics/DaySheet'
import {
  STATUS_LABEL,
  aggregate,
  defaultGrouping,
  type Grouping,
} from '@/components/analytics/aggregate'
import { MEASUREMENTS } from '@/lib/labels'
import { addDays, diffDays, formatDay, num, rangeLabel, todayIn } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { DailyRow, Measurement, MeasurementKind } from '@/types'

const PRESETS = [
  { value: '7', label: '7 дней', days: 7 },
  { value: '30', label: '30 дней', days: 30 },
  { value: '90', label: '90 дней', days: 90 },
  { value: '365', label: 'Год', days: 365 },
]
const GROUPINGS: { value: Grouping; label: string }[] = [
  { value: 'day', label: 'По дням' },
  { value: 'week', label: 'По неделям' },
  { value: 'month', label: 'По месяцам' },
]
const DAY = /^\d{4}-\d{2}-\d{2}$/

export default function AnalyticsPage() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState<DailyRow | null>(null)

  const preset = PRESETS.find((item) => item.value === params.get('period'))
  const customFrom = params.get('from') ?? ''
  const customTo = params.get('to') ?? ''
  const custom = !preset && DAY.test(customFrom) && DAY.test(customTo) && customFrom <= customTo
  const range = custom
    ? { from: customFrom, to: customTo }
    : { from: addDays(today, -((preset?.days ?? 30) - 1)), to: today }
  const period = custom ? 'custom' : (preset?.value ?? '30')
  const length = diffDays(range.to, range.from) + 1
  const requested = GROUPINGS.find((item) => item.value === params.get('group'))?.value
  const grouping = requested ?? defaultGrouping(length)
  const includePartial = params.get('partial') === '1'

  function update(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(values))
      if (value) next.set(key, value)
      else next.delete(key)
    setParams(next, { replace: true })
  }

  const daily = useQuery({
    queryKey: [...keys.daily, range.from, range.to],
    queryFn: ({ signal }) => analyticsApi.daily(range.from, range.to, { signal }),
    placeholderData: (previous) => previous,
  })
  const report = useQuery({
    queryKey: [...keys.report, range.from, range.to, includePartial],
    queryFn: ({ signal }) => analyticsApi.report(range.from, range.to, includePartial, { signal }),
    placeholderData: (previous) => previous,
  })
  const profile = useQuery({
    queryKey: keys.profile,
    queryFn: ({ signal }) => profileApi.get({ signal }),
  })
  const measurements = useQuery({
    queryKey: [...keys.measurements, range.from, range.to],
    queryFn: ({ signal }) => bodyApi.measurements({ start: range.from, end: range.to }, { signal }),
  })

  const buckets = useMemo(
    () => (daily.data ? aggregate(daily.data, grouping, includePartial) : []),
    [daily.data, grouping, includePartial],
  )
  const weightPoints: TrendPoint[] = buckets
    .filter((bucket) => bucket.weight !== null)
    .map((bucket) => ({
      key: bucket.key,
      label: bucket.label,
      title: bucket.title,
      value: bucket.weight,
    }))
  const logged = daily.data?.some((row) => row.status !== 'empty') ?? false
  const target = report.data?.targets.kcal ?? null
  const stale = daily.isPlaceholderData || report.isPlaceholderData

  return (
    <>
      <PageHeader title="Аналитика" />

      <div className="mb-5 flex flex-col gap-3" role="group" aria-label="Период и группировка">
        <div className="chips">
          {PRESETS.map((item) => (
            <button
              key={item.value}
              type="button"
              className="chip"
              aria-pressed={period === item.value}
              onClick={() => update({ period: item.value, from: null, to: null })}
            >
              {item.label}
            </button>
          ))}
          <DateRangePicker
            from={range.from}
            to={range.to}
            today={today}
            onChange={(from, to) => update({ period: null, from, to })}
            label={custom ? rangeLabel(range.from, range.to) : 'Свой период'}
            className={cn('chip', custom && 'border-primary bg-accent text-accent-foreground')}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="chips" aria-label="Группировка">
            {GROUPINGS.map((item) => (
              <button
                key={item.value}
                type="button"
                className="chip"
                aria-pressed={grouping === item.value}
                onClick={() => update({ group: item.value })}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex min-h-11 items-center gap-3">
            <Switch
              id="include-partial"
              checked={includePartial}
              onCheckedChange={(value) => update({ partial: value ? '1' : null })}
            />
            <Label htmlFor="include-partial" className="text-sm font-normal">
              Учитывать неполные дни
            </Label>
          </div>
        </div>
      </div>

      {daily.isError ? (
        <ErrorState error={daily.error} retry={() => daily.refetch()} />
      ) : daily.isPending ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-[330px] rounded-[20px]" />
          <Skeleton className="h-[330px] rounded-[20px]" />
        </div>
      ) : !logged && !weightPoints.length ? (
        <Card>
          <EmptyState
            icon={ChartColumnBig}
            title="За период нет данных"
            description={`${rangeLabel(range.from, range.to)}: ни записей о еде, ни взвешиваний. Выберите другой период.`}
          />
        </Card>
      ) : (
        <div className={cn('flex flex-col gap-4 transition-opacity', stale && 'opacity-60')}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Калории</CardTitle>
                <CardDescription>
                  {report.data?.averages.kcal != null
                    ? `В среднем ${num(report.data.averages.kcal)} ккал в день`
                    : grouping === 'day'
                      ? 'Нажмите на день, чтобы увидеть цифры'
                      : 'Среднее за день'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <CaloriesChart
                  data={buckets}
                  grouping={grouping}
                  target={target}
                  onSelect={
                    grouping === 'day' ? (bucket) => setSelected(bucket.rows[0]) : undefined
                  }
                />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Белки, жиры, углеводы</CardTitle>
                <CardDescription>
                  {grouping === 'day' ? 'Граммы за день' : 'Граммы в среднем за день'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <MacrosChart data={buckets} grouping={grouping} />
              </CardContent>
            </Card>
          </div>

          {report.isPending ? (
            <Skeleton className="h-80 rounded-[20px]" />
          ) : report.isError ? (
            <ErrorState error={report.error} retry={() => report.refetch()} />
          ) : (
            <ReportCard report={report.data} />
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Вес</CardTitle>
                <CardDescription>
                  {grouping === 'day'
                    ? 'Последнее взвешивание дня'
                    : 'Среднее за период группировки'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {weightPoints.length ? (
                  <TrendLine
                    points={weightPoints}
                    unit="кг"
                    name="Вес"
                    target={profile.data?.target_weight_kg}
                    targetLabel="цель"
                  />
                ) : (
                  <EmptyHint icon={Scale} text="Взвешиваний за период нет." />
                )}
              </CardContent>
            </Card>
            <MeasurementsCard query={measurements} />
          </div>

          <DaysTable rows={daily.data ?? []} onSelect={setSelected} />
        </div>
      )}

      <DaySheet row={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function EmptyHint({ icon: Icon, text }: { icon: typeof Scale; text: string }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center gap-3 rounded-[14px] border border-dashed text-sm text-muted-foreground">
      <Icon className="size-5" aria-hidden="true" />
      {text}
    </div>
  )
}

function MeasurementsCard({
  query,
}: {
  query: {
    data?: Measurement[]
    isPending: boolean
    isError: boolean
    error: Error | null
    refetch: () => unknown
  }
}) {
  const kinds = MEASUREMENTS.filter((kind) =>
    query.data?.some((entry) => entry.kind === kind.value),
  )
  const [chosen, setChosen] = useState<MeasurementKind | null>(null)
  const kind = kinds.find((item) => item.value === chosen) ?? kinds[0]
  const points: TrendPoint[] = (query.data ?? [])
    .filter((entry) => entry.kind === kind?.value)
    .sort((a, b) => (a.measured_at < b.measured_at ? -1 : 1))
    .map((entry) => ({
      key: String(entry.id),
      label: formatDay(entry.measured_on, 'd.MM'),
      title: formatDay(entry.measured_on, 'd MMMM yyyy'),
      value: entry.value,
    }))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Замеры</CardTitle>
        <CardDescription>{kind ? `${kind.label}, ${kind.unit}` : 'Объемы тела'}</CardDescription>
        {kinds.length > 1 && (
          <CardAction>
            <select
              className="h-11 rounded-xl border bg-card px-3 text-sm"
              value={kind?.value}
              onChange={(event) => setChosen(event.target.value as MeasurementKind)}
              aria-label="Какой замер показать"
            >
              {kinds.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {query.isPending ? (
          <BlockSkeleton rows={2} />
        ) : query.isError ? (
          <ErrorState error={query.error!} retry={() => query.refetch()} />
        ) : kind && points.length ? (
          <TrendLine points={points} unit={kind.unit} name={kind.label} />
        ) : (
          <EmptyHint icon={Ruler} text="Замеров за период нет." />
        )}
      </CardContent>
    </Card>
  )
}

function DaysTable({ rows, onSelect }: { rows: DailyRow[]; onSelect: (row: DailyRow) => void }) {
  const ordered = [...rows].reverse()
  return (
    <Card className="gap-0 py-0">
      <details className="group">
        <summary className="flex min-h-14 cursor-pointer items-center justify-between px-5 font-semibold select-none">
          По дням
          <span className="text-sm font-normal text-muted-foreground group-open:hidden">
            Показать таблицу
          </span>
        </summary>
        <div className="overflow-x-auto px-2 pb-3">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Данные по дням; строка открывает день</caption>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">День</th>
                <th className="px-3 py-2 text-right font-medium">Ккал</th>
                <th className="px-3 py-2 text-right font-medium">Б</th>
                <th className="px-3 py-2 text-right font-medium">Ж</th>
                <th className="px-3 py-2 text-right font-medium">У</th>
                <th className="px-3 py-2 text-right font-medium">Вес</th>
                <th className="px-3 py-2 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {ordered.map((row) => (
                <tr
                  key={row.day}
                  className={cn('border-t', row.status === 'empty' && 'text-muted-foreground')}
                >
                  <td className="px-1 py-0.5">
                    <button
                      type="button"
                      className="min-h-10 rounded-lg px-2 text-left hover:bg-muted"
                      onClick={() => onSelect(row)}
                    >
                      {formatDay(row.day, 'EEEEEE, d MMM')}
                    </button>
                  </td>
                  <td className="px-3 text-right">
                    {row.status === 'empty' ? '—' : num(row.kcal)}
                  </td>
                  <td className="px-3 text-right">
                    {row.status === 'empty' ? '—' : num(row.protein)}
                  </td>
                  <td className="px-3 text-right">{row.status === 'empty' ? '—' : num(row.fat)}</td>
                  <td className="px-3 text-right">
                    {row.status === 'empty' ? '—' : num(row.carbs)}
                  </td>
                  <td className="px-3 text-right">
                    {row.weight === null ? '—' : num(row.weight, 1)}
                  </td>
                  <td className="px-3 whitespace-nowrap">
                    {STATUS_LABEL[row.status]}
                    {row.marked && <span className="text-muted-foreground"> · вручную</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
