import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { profileApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { num, plural } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AiUsagePeriod } from '@/types'

const share = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0)
const usd = (value: number) => (value < 0.01 && value > 0 ? '< $0.01' : `$${value.toFixed(2)}`)

/** What the assistant costs in tokens: exact counts Codex reports for every request. */
export function AiUsageSection() {
  const [period, setPeriod] = useState<AiUsagePeriod['key']>('month')
  const usage = useQuery({
    queryKey: keys.aiUsage,
    queryFn: ({ signal }) => profileApi.aiUsage({ signal }),
  })
  const row = usage.data?.periods.find((item) => item.key === period)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Расход AI</CardTitle>
        <CardDescription>
          Токены, потраченные на ваши сообщения и разборы рациона. Codex сообщает их точно по
          каждому запросу.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {usage.isPending ? (
          <BlockSkeleton rows={3} />
        ) : usage.isError ? (
          <ErrorState error={usage.error} retry={() => usage.refetch()} />
        ) : (
          <>
            <div
              role="radiogroup"
              aria-label="Период"
              className="flex w-full rounded-[12px] bg-muted p-0.5 sm:w-fit"
            >
              {usage.data.periods.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  role="radio"
                  aria-checked={period === item.key}
                  onClick={() => setPeriod(item.key)}
                  className={cn(
                    'min-h-9 flex-1 rounded-[10px] px-3 text-[13px] font-medium whitespace-nowrap transition-colors sm:flex-none',
                    period === item.key
                      ? 'bg-card text-foreground shadow-sm dark:bg-white/10'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {row && row.requests === 0 ? (
              <p className="text-sm text-muted-foreground">За этот период ассистент не отвечал.</p>
            ) : (
              row && <Totals row={row} />
            )}

            <p className="text-xs text-muted-foreground">
              {usage.data.model && <>Модель {usage.data.model}. </>}
              Вход включает контекст: профиль, записи, память, фото.
              {!usage.data.priced && ' Стоимость появится, если задать цены в настройках сервера.'}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Totals({ row }: { row: AiUsagePeriod }) {
  const average = row.measured ? row.total / row.measured : null
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="hero-number">{num(row.total)}</span>
          <span className="text-muted-foreground">
            {plural(row.total, ['токен', 'токена', 'токенов'])}
          </span>
          {row.cost !== null && (
            <span className="serif-number ml-1 text-lg text-muted-foreground">
              ≈ {usd(row.cost)}
            </span>
          )}
        </p>
        <p className="mt-2 text-sm text-muted-foreground tabular">
          {num(row.requests)} {plural(row.requests, ['запрос', 'запроса', 'запросов'])}
          {average !== null && <>, в среднем {num(average)} на запрос</>}
        </p>
      </div>
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div className="rounded-[14px] bg-muted px-3.5 py-3">
          <dt className="text-xs text-muted-foreground">Вход</dt>
          <dd className="serif-number text-xl">{num(row.input)}</dd>
          <dd className="mt-0.5 text-xs text-muted-foreground tabular">
            из кэша {num(row.cached)} ({share(row.cached, row.input)}%)
          </dd>
        </div>
        <div className="rounded-[14px] bg-muted px-3.5 py-3">
          <dt className="text-xs text-muted-foreground">Ответ</dt>
          <dd className="serif-number text-xl">{num(row.output)}</dd>
          <dd className="mt-0.5 text-xs text-muted-foreground tabular">
            на рассуждения {num(row.reasoning)}
          </dd>
        </div>
      </dl>
      {row.measured < row.requests && (
        <p className="text-xs text-muted-foreground">
          Еще {num(row.requests - row.measured)}{' '}
          {plural(row.requests - row.measured, ['запрос', 'запроса', 'запросов'])} без данных о
          токенах: они были до учета.
        </p>
      )}
    </div>
  )
}
