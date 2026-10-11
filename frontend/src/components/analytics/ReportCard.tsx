import { ClipboardCopy, Printer } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { MACROS, measurement } from '@/lib/labels'
import { days, num, rangeLabel, signed } from '@/lib/format'
import { copyText } from '@/lib/clipboard'
import type { Report } from '@/types'

const ROWS = [
  { key: 'kcal', label: 'Калории', unit: 'ккал' },
  ...MACROS.map((macro) => ({ key: macro.key, label: macro.label, unit: 'г' })),
] as const

function deviation(value: number | null, target: number | null) {
  if (value === null || !target) return null
  return Math.round(((value - target) / target) * 100)
}

/** The period's numbers as plain text, to paste into a chat with a coach or a doctor. */
export function reportText(report: Report) {
  const lines = [
    `Сводный отчет: ${rangeLabel(report.start, report.end)}`,
    `Дней: ${report.days}; с записями: ${report.logged_days}; полных: ${report.complete_days}; в расчете: ${report.counted_days}${report.include_partial ? ' (с неполными)' : ''}`,
  ]
  for (const row of ROWS) {
    const value = report.averages[row.key]
    const target = report.targets[row.key]
    const diff = deviation(value, target)
    lines.push(
      `${row.label}: в среднем ${num(value)} ${row.unit}${target ? ` (цель ${num(target)}${diff !== null ? `, ${signed(diff, 0)}%` : ''})` : ''}`,
    )
  }
  if (report.macro_split)
    lines.push(
      `Доли калорий: Б ${report.macro_split.protein}% · Ж ${report.macro_split.fat}% · У ${report.macro_split.carbs}%`,
    )
  if (report.days_within_target !== null)
    lines.push(
      `В пределах ±10% от цели: ${report.days_within_target} из ${report.counted_days} дн.`,
    )
  if (report.weight)
    lines.push(
      `Вес: ${num(report.weight.first, 1)} → ${num(report.weight.last, 1)} кг (${signed(report.weight.change)} кг)`,
    )
  for (const item of report.measurements)
    lines.push(
      `${item.name}: ${num(item.first, 1)} → ${num(item.last, 1)} ${measurement(item.kind).unit} (${signed(item.change)})`,
    )
  if (report.top_foods.length)
    lines.push(
      `Чаще всего: ${report.top_foods.map((food) => `${food.name} (${food.count})`).join(', ')}`,
    )
  return lines.join('\n')
}

export function ReportCard({ report }: { report: Report }) {
  const split = report.macro_split
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Сводный отчет</CardTitle>
        <CardDescription>
          {rangeLabel(report.start, report.end)} · {days(report.days)}
        </CardDescription>
        <CardAction className="no-print flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Скопировать отчет текстом"
            title="Скопировать текстом"
            onClick={async () => {
              if (await copyText(reportText(report))) toast.success('Отчет скопирован')
              else toast.error('Не удалось скопировать')
            }}
          >
            <ClipboardCopy />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Печать"
            title="Печать"
            onClick={() => window.print()}
          >
            <Printer />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: 'Дней в периоде', value: report.days },
            { label: 'С записями', value: report.logged_days },
            { label: 'Полных', value: report.complete_days },
            { label: 'В расчете', value: report.counted_days },
          ].map((item) => (
            <div key={item.label} className="rounded-[14px] bg-muted px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">{item.label}</dt>
              <dd className="text-xl font-semibold">{item.value}</dd>
            </div>
          ))}
        </dl>
        {report.counted_days === 0 ? (
          <p className="text-sm text-muted-foreground">
            {report.logged_days
              ? 'Полных дней нет — включите «Учитывать неполные дни» или отметьте дни полными.'
              : 'За этот период записей нет.'}
          </p>
        ) : (
          <>
            <section aria-labelledby="report-averages" className="flex flex-col gap-2">
              <h3 id="report-averages" className="section-title">
                В среднем за день
              </h3>
              <div className="overflow-hidden rounded-[14px] border">
                <table className="w-full text-sm">
                  <thead className="bg-muted text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">&nbsp;</th>
                      <th className="px-3 py-2 text-right font-medium">Среднее</th>
                      <th className="px-3 py-2 text-right font-medium">Цель</th>
                      <th className="px-3 py-2 text-right font-medium">Разница</th>
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {ROWS.map((row) => {
                      const value = report.averages[row.key]
                      const target = report.targets[row.key]
                      const diff = deviation(value, target)
                      return (
                        <tr key={row.key} className="border-t">
                          <th scope="row" className="px-3 py-2.5 text-left font-medium">
                            <span className="flex items-center gap-2">
                              <span
                                className="macro-dot"
                                style={{ background: `var(--${row.key})` }}
                                aria-hidden="true"
                              />
                              {row.label}
                            </span>
                          </th>
                          <td className="px-3 py-2.5 text-right">
                            {num(value)} {row.unit}
                          </td>
                          <td className="px-3 py-2.5 text-right text-muted-foreground">
                            {target ? num(target) : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            {diff === null ? '—' : `${signed(diff, 0)}%`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {report.days_within_target !== null && (
                <p className="text-sm">
                  <span className="font-medium">
                    {report.days_within_target} из {report.counted_days}
                  </span>{' '}
                  <span className="text-muted-foreground">
                    дн. — калории в пределах ±10% от цели
                  </span>
                </p>
              )}
            </section>

            {split && (
              <section aria-labelledby="report-split" className="flex flex-col gap-2">
                <h3 id="report-split" className="section-title">
                  Доли калорий
                </h3>
                <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
                  {MACROS.map((macro) => (
                    <span
                      key={macro.key}
                      className={`bg-macro-${macro.key}`}
                      style={{ width: `${split[macro.key]}%` }}
                    />
                  ))}
                </div>
                <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {MACROS.map((macro) => (
                    <span key={macro.key} className="flex items-center gap-1.5">
                      <span className={`macro-dot bg-macro-${macro.key}`} aria-hidden="true" />
                      {macro.label} <span className="font-medium tabular">{split[macro.key]}%</span>
                    </span>
                  ))}
                </p>
              </section>
            )}
          </>
        )}

        {(report.weight || report.measurements.length > 0) && (
          <section aria-labelledby="report-body" className="flex flex-col gap-2">
            <h3 id="report-body" className="section-title">
              Тело
            </h3>
            <ul className="row-list rounded-[14px] border text-sm">
              {report.weight && (
                <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-2.5">
                  <span className="font-medium">Вес</span>
                  <span className="tabular">
                    {num(report.weight.first, 1)} → {num(report.weight.last, 1)} кг{' '}
                    <span className="font-medium">({signed(report.weight.change)})</span>
                    <span className="block text-right text-xs text-muted-foreground">
                      мин {num(report.weight.min, 1)} · макс {num(report.weight.max, 1)} ·
                      взвешиваний {report.weight.entries}
                    </span>
                  </span>
                </li>
              )}
              {report.measurements.map((item) => (
                <li
                  key={item.kind}
                  className="flex items-baseline justify-between gap-4 px-3 py-2.5"
                >
                  <span className="font-medium">{item.name}</span>
                  <span className="tabular">
                    {num(item.first, 1)} → {num(item.last, 1)} {measurement(item.kind).unit}{' '}
                    <span className="font-medium">({signed(item.change)})</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {report.top_foods.length > 0 && (
          <section aria-labelledby="report-foods" className="flex flex-col gap-2">
            <h3 id="report-foods" className="section-title">
              Чаще всего
            </h3>
            <ol className="flex flex-wrap gap-2">
              {report.top_foods.map((food) => (
                <li
                  key={food.name}
                  className="rounded-full bg-muted px-3 py-1.5 text-sm first-letter:uppercase"
                >
                  {food.name} <span className="text-muted-foreground tabular">×{food.count}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </CardContent>
    </Card>
  )
}
