import { useEffect, useId, useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Rectangle,
  ReferenceArea,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
  type MouseHandlerDataParam,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { MACROS } from '@/lib/labels'
import { num } from '@/lib/format'
import { AXIS, Hatch, Legend, TipBox, hovered } from './ChartBits'
import { STATUS_LABEL, type Bucket, type Grouping } from './aggregate'

const KCAL: ChartConfig = { kcal: { label: 'Калории', color: 'var(--kcal)' } }
const MACRO_CONFIG: ChartConfig = {
  protein: { label: 'Белки', color: 'var(--protein)' },
  fat: { label: 'Жиры', color: 'var(--fat)' },
  carbs: { label: 'Углеводы', color: 'var(--carbs)' },
}

function bucketNote(bucket: Bucket, grouping: Grouping) {
  if (bucket.status === 'empty') return 'Нет записей'
  if (grouping === 'day')
    return `${STATUS_LABEL[bucket.status]}${bucket.rows[0]?.marked ? ' (отмечен вами)' : ''}`
  if (bucket.status === 'partial') return `Только неполные дни: ${bucket.logged}`
  return `Среднее по ${bucket.counted} из ${bucket.total} дн.`
}

/** The bar under the finger or the last click: a whole day's column answers, not only the
 * thin bar, and the numbers stay above the chart. Starts at the latest bar with data. */
function usePicked(data: Bucket[]) {
  const latest = () => {
    for (let index = data.length - 1; index >= 0; index--)
      if (data[index].status !== 'empty') return index
    return data.length - 1
  }
  const [picked, setPicked] = useState(latest)
  // A new period or grouping: back to its latest bar.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setPicked(latest()), [data])
  const pick = (state: MouseHandlerDataParam) => {
    // A tap may come without the tooltip's index; the label under the finger is enough.
    const byLabel = data.findIndex((item) => item.label === state?.activeLabel)
    const raw = state?.activeTooltipIndex
    const index = byLabel >= 0 ? byLabel : raw === null || raw === undefined ? -1 : Number(raw)
    if (Number.isInteger(index) && index >= 0 && index < data.length) setPicked(index)
  }
  return { bucket: data[picked] as Bucket | undefined, pick }
}

function Readout({
  bucket,
  grouping,
  value,
  onOpen,
}: {
  bucket: Bucket
  grouping: Grouping
  value: ReactNode
  onOpen?: () => void
}) {
  return (
    <div className="flex min-h-14 items-center justify-between gap-3 rounded-[16px] bg-muted px-3.5 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium first-letter:uppercase">{bucket.title}</p>
        <p className="text-xs text-muted-foreground">{bucketNote(bucket, grouping)}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {value}
        {onOpen && (
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={onOpen}
            aria-label="Открыть день"
            title="Открыть день"
          >
            <ChevronRight />
          </Button>
        )}
      </div>
    </div>
  )
}

export function CaloriesChart({
  data,
  grouping,
  target,
  onSelect,
}: {
  data: Bucket[]
  grouping: Grouping
  target: number | null
  onSelect?: (bucket: Bucket) => void
}) {
  const hatch = `hatch-kcal-${useId().replace(/:/g, '')}`
  const { bucket, pick } = usePicked(data)
  return (
    <div className="flex flex-col gap-3">
      {bucket && (
        <Readout
          bucket={bucket}
          grouping={grouping}
          onOpen={
            onSelect && grouping === 'day' && bucket.status !== 'empty'
              ? () => onSelect(bucket)
              : undefined
          }
          value={
            bucket.kcal !== null && (
              <span className="text-right">
                <span className="serif-number block text-xl leading-tight">
                  {num(bucket.kcal)} <span className="font-sans text-xs font-normal">ккал</span>
                </span>
                {target && (
                  <span className="block text-xs text-muted-foreground tabular">
                    {Math.round((bucket.kcal / target) * 100)}% нормы
                  </span>
                )}
              </span>
            )
          }
        />
      )}
      <ChartContainer config={KCAL} className="aspect-auto h-[240px] w-full">
        <BarChart
          data={data}
          margin={{ top: 8, right: 4, left: 0, bottom: 0 }}
          accessibilityLayer
          onClick={pick}
          style={{ cursor: 'pointer' }}
        >
          <defs>
            <Hatch id={hatch} color="var(--kcal)" />
          </defs>
          <CartesianGrid vertical={false} />
          {bucket && (
            <ReferenceArea
              x1={bucket.label}
              x2={bucket.label}
              fill="var(--lime)"
              fillOpacity={0.35}
              ifOverflow="visible"
            />
          )}
          <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={10} />
          <YAxis {...AXIS} width={48} allowDecimals={false} tickFormatter={(value) => num(value)} />
          {target && (
            <ReferenceLine
              y={target}
              ifOverflow="extendDomain"
              stroke="var(--foreground)"
              strokeOpacity={0.55}
              strokeDasharray="4 4"
              label={{
                value: `цель ${num(target)}`,
                position: 'insideTopRight',
                fill: 'var(--muted-foreground)',
                fontSize: 11,
              }}
            />
          )}
          <Tooltip
            cursor={{ fill: 'var(--muted)', opacity: 0.6 }}
            content={(props) => {
              const bucket = hovered<Bucket>(props)
              if (!bucket) return null
              return (
                <TipBox
                  title={bucket.title}
                  rows={
                    bucket.kcal === null
                      ? []
                      : [
                          {
                            color: 'var(--kcal)',
                            label: grouping === 'day' ? 'Калории' : 'Калории в день',
                            value: `${num(bucket.kcal)} ккал`,
                            muted: bucket.status === 'partial',
                          },
                        ]
                  }
                  note={bucketNote(bucket, grouping)}
                />
              )
            }}
          />
          <Bar
            dataKey="kcal"
            maxBarSize={24}
            radius={[4, 4, 0, 0]}
            shape={(props: BarShapeProps) => (
              <Rectangle
                {...props}
                fill={data[props.index]?.status === 'partial' ? `url(#${hatch})` : 'var(--kcal)'}
              />
            )}
          />
        </BarChart>
      </ChartContainer>
      <Legend
        items={[
          { color: 'var(--kcal)', label: grouping === 'day' ? 'Полный день' : 'Среднее за день' },
          { color: 'var(--kcal)', label: 'Неполные данные', hatched: true },
        ]}
      />
    </div>
  )
}

export function MacrosChart({ data, grouping }: { data: Bucket[]; grouping: Grouping }) {
  const opacity = (index: number) => (data[index]?.status === 'partial' ? 0.4 : 1)
  const { bucket, pick } = usePicked(data)
  return (
    <div className="flex flex-col gap-3">
      {bucket && (
        <Readout
          bucket={bucket}
          grouping={grouping}
          value={
            bucket.status !== 'empty' && (
              <span className="flex flex-col items-end gap-0.5 text-xs tabular">
                {MACROS.map((macro) => (
                  <span key={macro.key} className="flex items-center gap-1.5">
                    <span className={`macro-dot bg-macro-${macro.key}`} aria-hidden="true" />
                    {macro.short} <span className="font-medium">{num(bucket[macro.key])} г</span>
                  </span>
                ))}
              </span>
            )
          }
        />
      )}
      <ChartContainer config={MACRO_CONFIG} className="aspect-auto h-[240px] w-full">
        <BarChart
          data={data}
          margin={{ top: 8, right: 4, left: 0, bottom: 0 }}
          accessibilityLayer
          onClick={pick}
          style={{ cursor: 'pointer' }}
        >
          <CartesianGrid vertical={false} />
          {bucket && (
            <ReferenceArea
              x1={bucket.label}
              x2={bucket.label}
              fill="var(--lime)"
              fillOpacity={0.35}
              ifOverflow="visible"
            />
          )}
          <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={10} />
          <YAxis {...AXIS} width={48} tickFormatter={(value) => num(value)} />
          <Tooltip
            cursor={{ fill: 'var(--muted)', opacity: 0.6 }}
            content={(props) => {
              const bucket = hovered<Bucket>(props)
              if (!bucket) return null
              return (
                <TipBox
                  title={bucket.title}
                  rows={
                    bucket.status === 'empty'
                      ? []
                      : MACROS.map((macro) => ({
                          color: `var(--${macro.key})`,
                          label: macro.label,
                          value: `${num(bucket[macro.key])} г`,
                          muted: bucket.status === 'partial',
                        }))
                  }
                  note={bucketNote(bucket, grouping)}
                />
              )
            }}
          />
          {MACROS.map((macro, position) => (
            <Bar
              key={macro.key}
              dataKey={macro.key}
              stackId="macros"
              maxBarSize={24}
              radius={position === MACROS.length - 1 ? [4, 4, 0, 0] : 0}
              shape={(props: BarShapeProps) => (
                <Rectangle
                  {...props}
                  fill={`var(--${macro.key})`}
                  fillOpacity={opacity(props.index)}
                  stroke="var(--card)"
                  strokeWidth={1}
                />
              )}
            />
          ))}
        </BarChart>
      </ChartContainer>
      <Legend
        items={MACROS.map((macro) => ({
          color: `var(--${macro.key})`,
          label: `${macro.label}, г`,
        }))}
      />
    </div>
  )
}
