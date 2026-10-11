import type { ReactNode } from 'react'

export interface TipRow {
  color: string
  label: string
  value: string
  muted?: boolean
}

/** Tooltip box in the app's style: a title, colored keys beside ink-colored values. */
export function TipBox({ title, rows, note }: { title: string; rows: TipRow[]; note?: ReactNode }) {
  return (
    <div className="grid min-w-[10rem] gap-1.5 rounded-xl border bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="font-medium first-letter:uppercase">{title}</p>
      {rows.map((row) => (
        <div key={row.label} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className="size-2.5 rounded-[3px]"
              style={{ background: row.color, opacity: row.muted ? 0.45 : 1 }}
              aria-hidden="true"
            />
            {row.label}
          </span>
          <span className="font-medium tabular">{row.value}</span>
        </div>
      ))}
      {note && <p className="text-muted-foreground">{note}</p>}
    </div>
  )
}

/** The data point under the pointer, typed by the caller. */
export function hovered<T>(props: {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: unknown }>
}): T | null {
  if (!props.active || !props.payload?.length) return null
  return (props.payload[0]?.payload as T) ?? null
}

export const AXIS = {
  tickLine: false,
  axisLine: false,
  tick: { fontSize: 12 },
} as const

/** Diagonal hatching for partial days: the same hue, quieter. */
export function Hatch({ id, color }: { id: string; color: string }) {
  return (
    <pattern
      id={id}
      patternUnits="userSpaceOnUse"
      width="6"
      height="6"
      patternTransform="rotate(45)"
    >
      <rect width="6" height="6" fill={color} fillOpacity="0.22" />
      <line x1="0" y1="0" x2="0" y2="6" stroke={color} strokeWidth="2.2" strokeOpacity="0.65" />
    </pattern>
  )
}

export function Legend({
  items,
}: {
  items: { color: string; label: string; hatched?: boolean }[]
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-[3px]"
            style={
              item.hatched
                ? {
                    background: `repeating-linear-gradient(45deg, ${item.color} 0 2px, transparent 2px 4px)`,
                    boxShadow: `inset 0 0 0 1px ${item.color}`,
                    opacity: 0.8,
                  }
                : { background: item.color }
            }
            aria-hidden="true"
          />
          {item.label}
        </li>
      ))}
    </ul>
  )
}
