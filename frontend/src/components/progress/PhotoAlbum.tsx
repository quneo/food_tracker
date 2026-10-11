import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Camera, ImagePlus, Maximize2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { bodyApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Photo } from '@/components/shared/Photo'
import { Lightbox } from '@/components/shared/Lightbox'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/States'
import { POSES, poseLabel } from '@/lib/labels'
import { formatDay, num, todayIn } from '@/lib/format'
import { PHOTO_TYPES } from '@/components/meals/MealPhotos'
import type { Pose, ProgressPhoto } from '@/types'

export function PhotoAlbum({ photos }: { photos: ProgressPhoto[] }) {
  const [pose, setPose] = useState<Pose | null>(null)
  const [uploading, setUploading] = useState(false)
  const [editing, setEditing] = useState<ProgressPhoto | null>(null)
  const shown = pose ? photos.filter((photo) => photo.pose === pose) : photos
  const months = useMemo(() => {
    const groups = new Map<string, ProgressPhoto[]>()
    for (const photo of shown) {
      const key = photo.taken_on.slice(0, 7)
      groups.set(key, [...(groups.get(key) ?? []), photo])
    }
    return [...groups.entries()]
  }, [shown])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="chips" role="group" aria-label="Ракурс">
          <button type="button" className="chip" aria-pressed={!pose} onClick={() => setPose(null)}>
            Все
          </button>
          {POSES.map((item) => (
            <button
              key={item.value}
              type="button"
              className="chip"
              aria-pressed={pose === item.value}
              onClick={() => setPose(pose === item.value ? null : item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <Button onClick={() => setUploading(true)}>
          <ImagePlus />
          Загрузить фото
        </Button>
      </div>

      {!photos.length ? (
        <EmptyState
          icon={Camera}
          title="Фото прогресса пока нет"
          description="Снимайте себя раз в неделю-две в одном ракурсе и при похожем свете — так изменения видно лучше. Можно прислать фото боту с подписью «прогресс»."
        />
      ) : !shown.length ? (
        <p className="text-sm text-muted-foreground">В этом ракурсе фото нет.</p>
      ) : (
        months.map(([month, list]) => (
          <section key={month} aria-labelledby={`month-${month}`} className="flex flex-col gap-3">
            <h2 id={`month-${month}`} className="text-base font-semibold first-letter:uppercase">
              {formatDay(`${month}-01`, 'LLLL yyyy')}
            </h2>
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {list.map((photo) => (
                <li key={photo.id}>
                  <button
                    type="button"
                    onClick={() => setEditing(photo)}
                    className="group block w-full overflow-hidden rounded-[16px] border bg-card text-left"
                  >
                    <Photo
                      id={photo.media_id}
                      alt={`${poseLabel(photo.pose)}, ${formatDay(photo.taken_on, 'd MMMM yyyy')}`}
                      className="aspect-[3/4] w-full transition-transform group-hover:scale-[1.02]"
                    />
                    <span className="flex flex-col px-3 py-2 text-sm">
                      <span className="font-medium whitespace-nowrap">
                        {formatDay(photo.taken_on, 'd MMM')}
                      </span>
                      <span className="truncate text-muted-foreground">
                        {poseLabel(photo.pose)}
                        {photo.weight_kg !== null && ` · ${num(photo.weight_kg, 1)} кг`}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      <UploadSheet open={uploading} onOpenChange={setUploading} />
      <PhotoSheet photo={editing} onClose={() => setEditing(null)} />
    </div>
  )
}

function PoseChips({ value, onChange }: { value: Pose; onChange: (pose: Pose) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium" id="pose-label">
        Ракурс
      </span>
      <div className="chips" role="radiogroup" aria-labelledby="pose-label">
        {POSES.map((item) => (
          <button
            key={item.value}
            type="button"
            role="radio"
            aria-checked={value === item.value}
            data-state={value === item.value ? 'on' : 'off'}
            className="chip"
            onClick={() => onChange(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function UploadSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <ResponsiveSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Фото прогресса"
      description="Фото видите только вы."
    >
      {open && <UploadForm onDone={() => onOpenChange(false)} />}
    </ResponsiveSheet>
  )
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const user = useUser()
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const today = todayIn(user.timezone)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [takenOn, setTakenOn] = useState(today)
  const [pose, setPose] = useState<Pose>('front')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Выберите фото')
      return bodyApi.uploadPhoto({
        file,
        taken_on: takenOn || undefined,
        pose,
        note: note.trim() || undefined,
      })
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.photos })
      toast.success('Фото загружено')
      onDone()
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        upload.mutate()
      }}
    >
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="grid aspect-[4/3] w-full place-items-center overflow-hidden rounded-[16px] border border-dashed bg-muted text-muted-foreground"
      >
        {preview ? (
          <img src={preview} alt="Выбранное фото" className="size-full object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-2 text-sm">
            <ImagePlus className="size-7" />
            Выбрать фото
          </span>
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null)
          event.target.value = ''
        }}
      />
      <div className="flex flex-col gap-2">
        <Label htmlFor="photo-date">Дата</Label>
        <Input
          id="photo-date"
          type="date"
          value={takenOn}
          max={today}
          onChange={(event) => setTakenOn(event.target.value)}
        />
      </div>
      <PoseChips value={pose} onChange={setPose} />
      <div className="flex flex-col gap-2">
        <Label htmlFor="photo-note">Заметка</Label>
        <Textarea
          id="photo-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
          rows={2}
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={upload.isPending || !file}>
        {upload.isPending ? 'Загружаем…' : 'Загрузить'}
      </Button>
    </form>
  )
}

function PhotoSheet({ photo, onClose }: { photo: ProgressPhoto | null; onClose: () => void }) {
  return (
    <ResponsiveSheet
      open={photo !== null}
      onOpenChange={(value) => !value && onClose()}
      title={photo ? formatDay(photo.taken_on, 'd MMMM yyyy') : ''}
      description={
        photo
          ? `${poseLabel(photo.pose)}${photo.weight_kg !== null ? ` · вес рядом с датой ${num(photo.weight_kg, 1)} кг` : ''}`
          : undefined
      }
    >
      {photo && <PhotoForm key={photo.id} photo={photo} onDone={onClose} />}
    </ResponsiveSheet>
  )
}

function PhotoForm({ photo, onDone }: { photo: ProgressPhoto; onDone: () => void }) {
  const user = useUser()
  const client = useQueryClient()
  const [takenOn, setTakenOn] = useState(photo.taken_on)
  const [pose, setPose] = useState<Pose>(photo.pose)
  const [note, setNote] = useState(photo.note ?? '')
  const [viewing, setViewing] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const dirty = takenOn !== photo.taken_on || pose !== photo.pose || note !== (photo.note ?? '')

  const save = useMutation({
    mutationFn: () =>
      bodyApi.updatePhoto(photo.id, { taken_on: takenOn, pose, note: note.trim() || null }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.photos })
      toast.success('Сохранено')
      onDone()
    },
  })
  const remove = useMutation({
    mutationFn: () => bodyApi.removePhoto(photo.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.photos })
      toast.success('Фото удалено')
      onDone()
    },
    onError: () => client.invalidateQueries({ queryKey: keys.photos }),
    meta: { silent: true },
  })

  const ratio = photo.width && photo.height ? photo.width / photo.height : 3 / 4
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div
        className="relative mx-auto w-full"
        style={{ maxWidth: `min(100%, calc(48dvh * ${ratio}))` }}
      >
        <Photo
          id={photo.media_id}
          alt={`${poseLabel(photo.pose)}, ${formatDay(photo.taken_on, 'd MMMM yyyy')}`}
          className="w-full rounded-[16px]"
          style={{ aspectRatio: String(ratio) }}
          eager
        />
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="absolute right-2 bottom-2 rounded-full bg-black/55 text-white hover:bg-black/70"
          onClick={() => setViewing(0)}
          aria-label="Открыть в полном размере"
        >
          <Maximize2 />
        </Button>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-photo-date">Дата</Label>
        <Input
          id="edit-photo-date"
          type="date"
          value={takenOn}
          max={todayIn(user.timezone)}
          onChange={(event) => setTakenOn(event.target.value)}
          required
        />
      </div>
      <PoseChips value={pose} onChange={setPose} />
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-photo-note">Заметка</Label>
        <Textarea
          id="edit-photo-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
          rows={2}
        />
      </div>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button
          type="button"
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => setDeleting(true)}
        >
          <Trash2 />
          Удалить фото
        </Button>
        <Button type="submit" disabled={!dirty || save.isPending}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </div>
      <Lightbox
        ids={[photo.media_id]}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title="Фото прогресса"
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Удалить фото?"
        description="Фото удалится из альбома и хранилища без возможности восстановления."
        onConfirm={() => remove.mutateAsync()}
      />
    </form>
  )
}
