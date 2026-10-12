import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { ArrowLeftRight, Columns2, GripVertical, Images, SquareSplitHorizontal } from 'lucide-react'
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
import { poseLabel } from '@/lib/labels'
import { days as daysText, diffDays, formatDay, num, signed } from '@/lib/format'
import type { ProgressPhoto } from '@/types'

const describe = (photo: ProgressPhoto) =>
  `${formatDay(photo.taken_on, 'd MMM yyyy')} · ${poseLabel(photo.pose)}${
    photo.weight_kg !== null ? ` · ${num(photo.weight_kg, 1)} кг` : ''
  }`

/** Defaults: the earliest and the latest photo of the most recently used pose that has two. */
function defaults(photos: ProgressPhoto[]) {
  const pose = photos.find(
    (photo) => photos.filter((other) => other.pose === photo.pose).length > 1,
  )?.pose
  const pool = pose ? photos.filter((photo) => photo.pose === pose) : photos
  return { before: pool[pool.length - 1].id, after: pool[0].id }
}

export function CompareView({ photos }: { photos: ProgressPhoto[] }) {
  const { version } = usePhotoLock()
  // The API lists photos newest first.
  const initial = useMemo(() => (photos.length > 1 ? defaults(photos) : null), [photos])
  const [beforeId, setBeforeId] = useState<number | null>(null)
  const [afterId, setAfterId] = useState<number | null>(null)
  const [mode, setMode] = useState<'slider' | 'side'>('slider')

  if (!initial)
    return (
      <EmptyState
        icon={Images}
        title="Нужно хотя бы два фото"
        description="Загрузите фото в разные дни — здесь можно будет сравнить их рядом или шторкой."
      />
    )

  const before =
    photos.find((photo) => photo.id === beforeId) ?? photos.find((p) => p.id === initial.before)!
  const after =
    photos.find((photo) => photo.id === afterId) ?? photos.find((p) => p.id === initial.after)!
  const span = diffDays(after.taken_on, before.taken_on)
  const delta =
    before.weight_kg !== null && after.weight_kg !== null
      ? after.weight_kg - before.weight_kg
      : null

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-end">
        <PhotoPicker
          id="before"
          label="До"
          value={before.id}
          photos={photos}
          onChange={setBeforeId}
        />
        <Button
          variant="ghost"
          size="icon"
          className="justify-self-center"
          onClick={() => {
            setBeforeId(after.id)
            setAfterId(before.id)
          }}
          aria-label="Поменять местами"
          title="Поменять местами"
        >
          <ArrowLeftRight />
        </Button>
        <PhotoPicker
          id="after"
          label="После"
          value={after.id}
          photos={photos}
          onChange={setAfterId}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-medium">{span === 0 ? 'Один день' : daysText(Math.abs(span))}</span>
          {delta !== null && (
            <>
              <span className="text-muted-foreground"> · вес </span>
              <span className="font-medium tabular">{signed(delta)} кг</span>
            </>
          )}
          {before.pose !== after.pose && (
            <span className="text-muted-foreground"> · разные ракурсы</span>
          )}
        </p>
        <div className="chips" role="group" aria-label="Вид сравнения">
          <button
            type="button"
            className="chip"
            aria-pressed={mode === 'slider'}
            onClick={() => setMode('slider')}
          >
            <SquareSplitHorizontal />
            Шторка
          </button>
          <button
            type="button"
            className="chip"
            aria-pressed={mode === 'side'}
            onClick={() => setMode('side')}
          >
            <Columns2 />
            Рядом
          </button>
        </div>
      </div>

      {mode === 'slider' ? (
        <CompareSlider before={before} after={after} version={version} />
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:gap-3">
          {[
            { photo: before, label: 'До' },
            { photo: after, label: 'После' },
          ].map(({ photo, label }) => (
            <figure key={label} className="flex flex-col gap-2">
              <Photo
                id={photo.media_id}
                alt={`${label}: ${describe(photo)}`}
                className="w-full rounded-[16px]"
                style={{ aspectRatio: `${photo.width || 3} / ${photo.height || 4}` }}
                fit="cover"
                version={version}
              />
              <figcaption className="text-sm">
                <span className="font-medium">{label}</span>{' '}
                <span className="text-muted-foreground">{describe(photo)}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  )
}

function PhotoPicker({
  id,
  label,
  value,
  photos,
  onChange,
}: {
  id: string
  label: string
  value: number
  photos: ProgressPhoto[]
  onChange: (id: number) => void
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={`compare-${id}`}>{label}</Label>
      <Select value={String(value)} onValueChange={(next) => onChange(Number(next))}>
        <SelectTrigger id={`compare-${id}`} className="min-w-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper" className="max-h-72">
          {photos.map((photo) => (
            <SelectItem key={photo.id} value={String(photo.id)}>
              {describe(photo)}
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
  before: ProgressPhoto
  after: ProgressPhoto
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
        <span className="compare-label left-3">До · {formatDay(before.taken_on, 'd MMM')}</span>
        <span className="compare-label right-3">После · {formatDay(after.taken_on, 'd MMM')}</span>
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
