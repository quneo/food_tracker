import { useId } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Rectangle,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
} from 'recharts'
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
  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={KCAL} className="aspect-auto h-[240px] w-full">
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} accessibilityLayer>
          <defs>
            <Hatch id={hatch} color="var(--kcal)" />
          </defs>
          <CartesianGrid vertical={false} />
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
                  note={
                    <>
                      {bucketNote(bucket, grouping)}
                      {onSelect && grouping === 'day' && (
                        <span className="block">Нажмите, чтобы открыть день</span>
                      )}
                    </>
                  }
                />
              )
            }}
          />
          <Bar
            dataKey="kcal"
            maxBarSize={24}
            radius={[4, 4, 0, 0]}
            onClick={(_, index) => onSelect?.(data[index])}
            style={{ cursor: onSelect ? 'pointer' : undefined }}
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
  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={MACRO_CONFIG} className="aspect-auto h-[240px] w-full">
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} accessibilityLayer>
          <CartesianGrid vertical={false} />
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
