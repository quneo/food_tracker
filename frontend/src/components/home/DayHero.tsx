import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { MACROS } from '@/lib/labels'
import { num } from '@/lib/format'
import type { DaySummary } from '@/types'

/** The day's budget: what is left (or how far over), a hatched track, and the macros. */
export function DayHero({ summary, isToday }: { summary: DaySummary; isToday: boolean }) {
  const { totals, targets } = summary
  const target = targets.kcal
  const eaten = totals.kcal
  const left = target !== null ? Math.round(target - eaten) : null
  const share = target ? eaten / target : 0
  const over = left !== null && left < 0
  return (
    <section className="hero-card flex flex-col gap-5" aria-label="Калории за день">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="hero-muted text-sm font-medium">
            {target === null
              ? 'Съедено'
              : over
                ? 'Больше нормы на'
                : isToday
                  ? 'Осталось'
                  : 'Не добрали'}
          </p>
          <p className="mt-1 flex items-baseline gap-2">
            <span className="hero-number text-[52px] max-[420px]:text-[44px]">
              {num(target === null ? eaten : Math.abs(left!))}
            </span>
            <span className="text-lg font-medium">ккал</span>
          </p>
        </div>
        {target !== null && (
          <div className="shrink-0 text-right">
            <p className="serif-number text-[28px] leading-none">{Math.round(share * 100)}%</p>
            <p className="hero-muted mt-1.5 text-xs">нормы</p>
          </div>
        )}
      </div>
      {target !== null ? (
        <div className="flex flex-col gap-2">
          <div
            className="striped-track"
            role="progressbar"
            aria-label="Калории"
            aria-valuemin={0}
            aria-valuemax={target}
            aria-valuenow={Math.round(eaten)}
          >
            <span
              className={over ? 'is-over' : undefined}
              style={{ width: `${Math.min(share, 1) * 100}%` }}
            />
          </div>
          <p className="hero-muted flex justify-between gap-3 text-sm tabular">
            <span>
              Съедено <span className="font-semibold text-[var(--hero-ink)]">{num(eaten)}</span>
              {summary.drafts > 0 && ', черновики не в счет'}
            </span>
            <span>из {num(target)}</span>
          </p>
        </div>
      ) : (
        <p className="hero-muted text-sm">
          Норма не задана.{' '}
          <Link to="/profile" className="font-medium underline underline-offset-4">
            Рассчитать в профиле
          </Link>
        </p>
      )}
      <div className="grid grid-cols-3 gap-3 border-t border-[color-mix(in_srgb,var(--hero-ink)_12%,transparent)] pt-4">
        {MACROS.map((macro) => {
          const value = totals[macro.key]
          const goal = targets[macro.key]
          const part = goal ? value / goal : 0
          return (
            <div key={macro.key} className="flex min-w-0 flex-col gap-1.5">
              <span className="hero-muted truncate text-xs">{macro.label}</span>
              <span className="tabular text-[15px] leading-none">
                <span className="font-semibold">{num(value)}</span>
                <span className="hero-muted text-xs">{goal ? ` / ${num(goal)} г` : ' г'}</span>
              </span>
              {goal ? (
                <div
                  className="striped-track is-thin"
                  role="progressbar"
                  aria-label={macro.label}
                  aria-valuemin={0}
                  aria-valuemax={goal}
                  aria-valuenow={Math.round(value)}
                  style={{ '--fill': `var(--${macro.key})` } as CSSProperties}
                >
                  <span
                    className={part > 1.1 ? 'is-over' : undefined}
                    style={{
                      width: `${Math.min(part, 1) * 100}%`,
                      background: `var(--${macro.key})`,
                    }}
                  />
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}
