import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { ArrowLeftRight, GripVertical, Images } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Photo } from '@/components/shared/Photo'
import { EmptyState } from '@/components/shared/States'
import { mediaUrl } from '@/api/client'
import { usePhotoLock } from '@/hooks/usePhotoLock'
import { POSES, poseLabel } from '@/lib/labels'
import { days as daysText, diffDays, formatDay, num, signed } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Pose, ProgressEntry } from '@/types'

/** One photo of one day in one angle. */
interface Shot {
  id: number
  media_id: number
  width: number
  height: number
  taken_on: string
  pose: Pose
  weight_kg: number | null
}

const describe = (shot: Shot) =>
  `${formatDay(shot.taken_on, 'd MMM yyyy')}${
    shot.weight_kg !== null ? `, ${num(shot.weight_kg, 1)} кг` : ''
  }`

/** "14 сентября", with the year only when it is not this one: fits a narrow picker. */
const shortDay = (day: string) =>
  formatDay(day, day.slice(0, 4) === String(new Date().getFullYear()) ? 'd MMMM' : 'd MMM yyyy')

/** Pick the angle, then two days that have it; the earliest and the latest by default. */
export function CompareView({ entries }: { entries: ProgressEntry[] }) {
  const { version } = usePhotoLock()
  // Entries come newest first: so do the shots of each angle.
  const byPose = useMemo(() => {
    const groups = new Map<Pose, Shot[]>()
    for (const entry of entries)
      for (const pose of POSES) {
        const photo = entry.photos.find((item) => item.pose === pose.value)
        if (photo)
          groups.set(pose.value, [
            ...(groups.get(pose.value) ?? []),
            { ...photo, taken_on: entry.taken_on, weight_kg: entry.weight_kg },
          ])
      }
    return groups
  }, [entries])
  const comparable = POSES.filter((pose) => (byPose.get(pose.value)?.length ?? 0) > 1)
  const [choice, setChoice] = useState<{ pose: Pose | null; before?: number; after?: number }>({
    pose: null,
  })
  const [mode, setMode] = useState<'slider' | 'side'>('slider')

  if (!comparable.length)
    return (
      <EmptyState
        icon={Images}
        title="Пока не с чем сравнить"
        description="Нужны хотя бы две записи с одним ракурсом, например спереди в разные дни."
      />
    )

  const pose = choice.pose ?? comparable[0].value
  const shots = byPose.get(pose)!
  const before = shots.find((shot) => shot.id === choice.before) ?? shots[shots.length - 1]
  const after = shots.find((shot) => shot.id === choice.after) ?? shots[0]
  const span = diffDays(after.taken_on, before.taken_on)
  const delta =
    before.weight_kg !== null && after.weight_kg !== null
      ? after.weight_kg - before.weight_kg
      : null

  return (
    <div className="flex flex-col gap-4">
      <div className="glass flex flex-col gap-4 rounded-[24px] p-4 sm:p-5">
        <Segmented
          label="Ракурс"
          value={pose}
          options={POSES.map((item) => ({
            value: item.value,
            label: item.label,
            disabled: (byPose.get(item.value)?.length ?? 0) < 2,
          }))}
          onChange={(value) => setChoice({ pose: value })}
        />
        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2">
          <ShotPicker
            id="before"
            label="До"
            value={before.id}
            shots={shots}
            onChange={(id) => setChoice({ ...choice, pose, before: id })}
          />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setChoice({ pose, before: after.id, after: before.id })}
            aria-label="Поменять местами"
            title="Поменять местами"
          >
            <ArrowLeftRight />
          </Button>
          <ShotPicker
            id="after"
            label="После"
            value={after.id}
            shots={shots}
            onChange={(id) => setChoice({ ...choice, pose, after: id })}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[15px]">
            <span className="font-medium">
              {span === 0 ? 'Один день' : daysText(Math.abs(span))}
            </span>
            {delta !== null && (
              <span className="text-muted-foreground">
                , вес{' '}
                <span className="font-medium text-foreground tabular">{signed(delta)} кг</span>
              </span>
            )}
          </p>
          <Segmented
            label="Вид сравнения"
            value={mode}
            options={[
              { value: 'slider', label: 'Шторка' },
              { value: 'side', label: 'Рядом' },
            ]}
            onChange={setMode}
          />
        </div>
      </div>

      {mode === 'slider' ? (
        <CompareSlider before={before} after={after} version={version} />
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:gap-3">
          {[
            { shot: before, label: 'До' },
            { shot: after, label: 'После' },
          ].map(({ shot, label }) => (
            <figure key={label} className="flex flex-col gap-2">
              <Photo
                id={shot.media_id}
                alt={`${label}: ${poseLabel(shot.pose)}, ${describe(shot)}`}
                className="w-full rounded-[16px]"
                style={{ aspectRatio: `${shot.width || 3} / ${shot.height || 4}` }}
                fit="cover"
                version={version}
              />
              <figcaption className="text-sm">
                <span className="font-medium">{label}</span>{' '}
                <span className="text-muted-foreground">{describe(shot)}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  )
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string; disabled?: boolean }[]
  onChange: (value: T) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex rounded-[12px] bg-muted p-0.5 sm:w-fit"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            'min-h-9 flex-1 rounded-[10px] px-3 text-[13.5px] font-medium whitespace-nowrap transition-colors disabled:opacity-40 sm:flex-none',
            value === option.value
              ? 'bg-card text-foreground shadow-sm dark:bg-white/10'
              : 'text-muted-foreground enabled:hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function ShotPicker({
  id,
  label,
  value,
  shots,
  onChange,
}: {
  id: string
  label: string
  value: number
  shots: Shot[]
  onChange: (id: number) => void
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={`compare-${id}`} className="text-muted-foreground">
        {label}
      </Label>
      <Select value={String(value)} onValueChange={(next) => onChange(Number(next))}>
        <SelectTrigger id={`compare-${id}`} className="w-full min-w-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper" className="max-h-72">
          {shots.map((shot) => (
            <SelectItem key={shot.id} value={String(shot.id)}>
              {shortDay(shot.taken_on)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

/** Before on the left, after on the right; drag, tap or use the keyboard to move the edge. */
export function CompareSlider({
  before,
  after,
  version = '',
}: {
  before: Shot
  after: Shot
  version?: string
}) {
  const [position, setPosition] = useState(50)
  const box = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const ratio = after.width && after.height ? after.width / after.height : 3 / 4

  function moveTo(clientX: number) {
    const rect = box.current?.getBoundingClientRect()
    if (!rect || !rect.width) return
    setPosition(clamp(((clientX - rect.left) / rect.width) * 100))
  }
  function down(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    dragging.current = true
    event.currentTarget.setPointerCapture(event.pointerId)
    moveTo(event.clientX)
  }
  function move(event: PointerEvent<HTMLDivElement>) {
    if (dragging.current) moveTo(event.clientX)
  }
  function up(event: PointerEvent<HTMLDivElement>) {
    dragging.current = false
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId)
  }
  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 10 : 2
    const next: Record<string, number> = {
      ArrowLeft: position - step,
      ArrowDown: position - step,
      ArrowRight: position + step,
      ArrowUp: position + step,
      PageDown: position - 10,
      PageUp: position + 10,
      Home: 0,
      End: 100,
    }
    if (event.key in next) {
      event.preventDefault()
      setPosition(clamp(next[event.key]))
    }
  }

  return (
    <div className="mx-auto w-full" style={{ maxWidth: `min(100%, calc(72dvh * ${ratio}))` }}>
      <div
        ref={box}
        className="compare"
        style={{ aspectRatio: String(ratio) }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        <img
          src={mediaUrl(after.media_id, 'preview', version)}
          alt={`После: ${describe(after)}`}
          draggable={false}
        />
        <img
          src={mediaUrl(before.media_id, 'preview', version)}
          alt={`До: ${describe(before)}`}
          draggable={false}
          style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        />
        <span className="compare-label left-3">До, {formatDay(before.taken_on, 'd MMM')}</span>
        <span className="compare-label right-3">После, {formatDay(after.taken_on, 'd MMM')}</span>
        <span className="compare-divider" style={{ left: `${position}%` }} aria-hidden="true" />
        <div
          role="slider"
          tabIndex={0}
          aria-label="Граница между фото «до» и «после»"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(position)}
          aria-valuetext={`«До» занимает ${Math.round(position)}%`}
          aria-orientation="horizontal"
          className="compare-handle"
          style={{ left: `clamp(22px, ${position}%, calc(100% - 22px))` }}
          onKeyDown={keys}
        >
          <GripVertical className="size-5" aria-hidden="true" />
        </div>
      </div>
    </div>
  )
}
