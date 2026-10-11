import { CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { num } from '@/lib/format'
import { AXIS, TipBox, hovered } from './ChartBits'

export interface TrendPoint {
  key: string
  label: string
  title: string
  value: number | null
}

const CONFIG: ChartConfig = { value: { label: 'Значение', color: 'var(--primary)' } }

/** One measure over time: a 2px line, dots with a surface ring, gaps bridged. */
export function TrendLine({
  points,
  unit,
  name,
  digits = 1,
  target,
  targetLabel = 'цель',
  height = 220,
  compact = false,
}: {
  points: TrendPoint[]
  unit: string
  name: string
  digits?: number
  target?: number | null
  targetLabel?: string
  height?: number
  compact?: boolean
}) {
  const values = points
    .map((point) => point.value)
    .filter((value): value is number => value !== null)
  if (target) values.push(target)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pad = Math.max((max - min) * 0.15, 0.5)
  const many = points.filter((point) => point.value !== null).length > 40
  return (
    <ChartContainer config={CONFIG} className="aspect-auto w-full" style={{ height }}>
      <LineChart
        data={points}
        margin={
          compact
            ? { top: 6, right: 6, left: 6, bottom: 0 }
            : { top: 10, right: 8, left: 0, bottom: 0 }
        }
        accessibilityLayer
      >
        {!compact && <CartesianGrid vertical={false} />}
        <XAxis
          dataKey="label"
          {...AXIS}
          hide={compact}
          interval="preserveStartEnd"
          minTickGap={18}
        />
        <YAxis
          {...AXIS}
          hide={compact}
          width={48}
          domain={[Math.floor((min - pad) * 2) / 2, Math.ceil((max + pad) * 2) / 2]}
          tickFormatter={(value) => num(value, digits)}
        />
        {target ? (
          <ReferenceLine
            y={target}
            stroke="var(--foreground)"
            strokeOpacity={0.5}
            strokeDasharray="4 4"
            label={
              compact
                ? undefined
                : {
                    value: `${targetLabel} ${num(target, digits)}`,
                    position: 'insideTopRight',
                    fill: 'var(--muted-foreground)',
                    fontSize: 11,
                  }
            }
          />
        ) : null}
        <Tooltip
          cursor={{ stroke: 'var(--border)' }}
          content={(props) => {
            const point = hovered<TrendPoint>(props)
            if (!point || point.value === null) return null
            return (
              <TipBox
                title={point.title}
                rows={[
                  {
                    color: 'var(--primary)',
                    label: name,
                    value: `${num(point.value, digits)} ${unit}`,
                  },
                ]}
              />
            )
          }}
        />
        <Line
          dataKey="value"
          type="monotone"
          stroke="var(--primary)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          connectNulls
          dot={
            many ? false : { r: 4, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }
          }
          activeDot={{ r: 5, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  )
}
