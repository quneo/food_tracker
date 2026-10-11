import { Link } from 'react-router-dom'
import { MACROS } from '@/lib/labels'
import { num } from '@/lib/format'
import type { Targets, Totals } from '@/types'

const SIZE = 168
const STROKE = 14
const RADIUS = (SIZE - STROKE) / 2
const LENGTH = 2 * Math.PI * RADIUS

/** Eaten calories against the target: the ring fills up, the excess wraps in red. */
export function CalorieRing({ eaten, target }: { eaten: number; target: number | null }) {
  const share = target ? eaten / target : 0
  const main = Math.min(share, 1)
  const over = target ? Math.min(Math.max(share - 1, 0), 1) : 0
  const left = target ? Math.round(target - eaten) : null
  const label =
    target === null
      ? `Съедено ${num(eaten)} ккал`
      : left !== null && left >= 0
        ? `Съедено ${num(eaten)} из ${num(target)} ккал, осталось ${num(left)}`
        : `Съедено ${num(eaten)} из ${num(target)} ккал, больше цели на ${num(-left!)}`
  return (
    <div className="relative mx-auto size-[168px] shrink-0" role="img" aria-label={label}>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="size-full -rotate-90" aria-hidden="true">
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          strokeWidth={STROKE}
          className="ring-track"
        />
        {target !== null && (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={LENGTH}
            strokeDashoffset={LENGTH * (1 - main)}
            className="ring-value"
            style={{ opacity: main === 0 ? 0 : 1 }}
          />
        )}
        {over > 0 && (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={LENGTH}
            strokeDashoffset={LENGTH * (1 - over)}
            className="ring-value ring-over"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        {target === null ? (
          <>
            <span className="hero-number">{num(eaten)}</span>
            <span className="mt-1 text-sm text-muted-foreground">ккал съедено</span>
          </>
        ) : left! >= 0 ? (
          <>
            <span className="hero-number">{num(left)}</span>
            <span className="mt-1 text-sm text-muted-foreground">ккал осталось</span>
          </>
        ) : (
          <>
            <span className="hero-number text-destructive">+{num(-left!)}</span>
            <span className="mt-1 text-sm text-muted-foreground">ккал сверх цели</span>
          </>
        )}
      </div>
    </div>
  )
}

/** Protein, fat and carbs against their targets, or just the numbers. */
export function MacroTargets({ totals, targets }: { totals: Totals; targets: Targets }) {
  return (
    <div className="flex flex-col gap-3.5">
      {MACROS.map((macro) => {
        const value = totals[macro.key]
        const target = targets[macro.key]
        const share = target ? Math.min(value / target, 1) : 0
        return (
          <div key={macro.key} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="flex items-center gap-2">
                <span className={`macro-dot bg-macro-${macro.key}`} aria-hidden="true" />
                {macro.label}
              </span>
              <span className="tabular">
                <span className="font-medium">{num(value)}</span>
                <span className="text-muted-foreground">
                  {target ? ` / ${num(target)} г` : ' г'}
                </span>
              </span>
            </div>
            {target ? (
              <div
                className="macro-bar"
                role="progressbar"
                aria-label={macro.label}
                aria-valuemin={0}
                aria-valuemax={target}
                aria-valuenow={Math.round(value)}
              >
                <span className={`bg-macro-${macro.key}`} style={{ width: `${share * 100}%` }} />
              </div>
            ) : null}
          </div>
        )
      })}
      {targets.protein === null && targets.fat === null && targets.carbs === null && (
        <p className="text-sm text-muted-foreground">
          Цели по БЖУ не заданы.{' '}
          <Link
            to="/profile"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Задать в профиле
          </Link>
        </p>
      )}
    </div>
  )
}
