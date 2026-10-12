import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Camera, ImagePlus, Lock, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { bodyApi } from '@/api/endpoints'
import { invalidateBody } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { usePhotoLock } from '@/hooks/usePhotoLock'
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
import { cn } from '@/lib/utils'
import { PHOTO_TYPES } from '@/components/meals/MealPhotos'
import { LockHint, PinSheet } from './PhotoLock'
import type { Pose, ProgressEntry } from '@/types'

const MAX_FILES = 6
/** Several photos at once: front, back, side, then other (as the server does for the bot). */
const nextPoses = (count: number, taken: Pose[] = []): Pose[] => {
  const free = (['front', 'back', 'side'] as Pose[]).filter((pose) => !taken.includes(pose))
  return Array.from({ length: count }, (_, index) => free[index] ?? 'other')
}

export function PhotoAlbum({
  entries,
  onCreate,
}: {
  entries: ProgressEntry[]
  onCreate: () => void
}) {
  const { version, hidden } = usePhotoLock()
  const [openId, setOpenId] = useState<number | null>(null)
  // Hidden photos ask for the code first, then the entry opens.
  const [askingFor, setAskingFor] = useState<number | null>(null)
  const months = useMemo(() => {
    const groups = new Map<string, ProgressEntry[]>()
    for (const entry of entries) {
      const key = entry.taken_on.slice(0, 7)
      groups.set(key, [...(groups.get(key) ?? []), entry])
    }
    return [...groups.entries()]
  }, [entries])
  const opened = entries.find((entry) => entry.id === openId) ?? null

  if (!entries.length)
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          icon={Camera}
          title="Фото прогресса пока нет"
          description="Снимайте себя раз в неделю-две при похожем свете: спереди, сбоку, сзади. Можно прислать фото боту с подписью «прогресс»."
        >
          <Button onClick={onCreate}>
            <ImagePlus />
            Новая запись
          </Button>
        </EmptyState>
        <LockHint />
      </div>
    )

  return (
    <div className="flex flex-col gap-4">
      {months.map(([month, list]) => (
        <section key={month} aria-labelledby={`month-${month}`} className="album-month glass">
          <h2 id={`month-${month}`} className="album-month-title">
            {formatDay(`${month}-01`, 'LLLL yyyy')}
          </h2>
          <ol className="album-days">
            {list.map((entry) => (
              <li key={entry.id}>
                <AlbumDay
                  entry={entry}
                  version={version}
                  hidden={hidden}
                  onOpen={() => (hidden ? setAskingFor(entry.id) : setOpenId(entry.id))}
                />
              </li>
            ))}
          </ol>
        </section>
      ))}
      <LockHint />

      <PinSheet
        open={askingFor !== null}
        onOpenChange={(value) => !value && setAskingFor(null)}
        onUnlocked={() => setOpenId(askingFor)}
      />
      <ResponsiveSheet
        open={opened !== null}
        onOpenChange={(value) => !value && setOpenId(null)}
        title={opened ? formatDay(opened.taken_on, 'd MMMM yyyy') : ''}
        description={
          opened?.weight_kg != null
            ? `Вес рядом с этой датой: ${num(opened.weight_kg, 1)} кг`
            : undefined
        }
        wide
      >
        {opened && (
          <EntryForm
            key={opened.id}
            entry={opened}
            version={version}
            onClose={() => setOpenId(null)}
          />
        )}
      </ResponsiveSheet>
    </div>
  )
}

export function NewEntrySheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <ResponsiveSheet open={open} onOpenChange={onOpenChange} title="Новая запись" wide>
      {open && <UploadForm onDone={() => onOpenChange(false)} />}
    </ResponsiveSheet>
  )
}

/** One day on the album's line: the date and weight, then that day's photos side by side. */
function AlbumDay({
  entry,
  version,
  hidden,
  onOpen,
}: {
  entry: ProgressEntry
  version: string
  hidden: boolean
  onOpen: () => void
}) {
  const shown = entry.photos.slice(0, 4)
  const day = formatDay(entry.taken_on, 'd MMMM')
  return (
    <button type="button" onClick={onOpen} className="album-day" aria-label={`${day}: открыть`}>
      <span className="album-day-head">
        <span className="album-day-date">{day}</span>
        {entry.weight_kg !== null && (
          <span className="serif-number text-[15px] text-muted-foreground">
            {num(entry.weight_kg, 1)} кг
          </span>
        )}
      </span>
      <span className="album-shots">
        {shown.map((photo, index) => (
          <span key={photo.id} className="album-shot">
            <span className="relative block">
              <Photo
                id={photo.media_id}
                alt={`${poseLabel(photo.pose)}, ${formatDay(entry.taken_on, 'd MMMM yyyy')}`}
                className="aspect-[3/4] w-full rounded-[14px]"
                version={version}
              />
              {hidden && (
                <Lock
                  className="absolute top-2 right-2 size-4 text-white/85 drop-shadow"
                  aria-hidden="true"
                />
              )}
              {index === 3 && entry.photos.length > 4 && (
                <span className="absolute inset-0 grid place-items-center rounded-[14px] bg-black/45 text-lg font-medium text-white">
                  +{entry.photos.length - 4}
                </span>
              )}
            </span>
            <span className="album-shot-pose">{poseLabel(photo.pose)}</span>
          </span>
        ))}
      </span>
      {entry.note && <span className="album-note">{entry.note}</span>}
    </button>
  )
}

function PoseSelect({
  value,
  onChange,
  label,
  disabled,
}: {
  value: Pose
  onChange: (pose: Pose) => void
  label: string
  disabled?: boolean
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as Pose)}
      aria-label={label}
      disabled={disabled}
      className="h-9 w-full rounded-[10px] border bg-card px-2 text-sm"
    >
      {POSES.map((pose) => (
        <option key={pose.value} value={pose.value}>
          {pose.label}
        </option>
      ))}
    </select>
  )
}

interface Picked {
  key: string
  file: File
  url: string
  pose: Pose
}

/** Picks files and keeps their previews; the previews are released when dropped. */
function usePicked() {
  const [picked, setPicked] = useState<Picked[]>([])
  const urls = useRef<string[]>([])
  useEffect(() => () => urls.current.forEach((url) => URL.revokeObjectURL(url)), [])
  function add(files: File[], taken: Pose[]) {
    setPicked((current) => {
      const room = MAX_FILES - current.length
      const fresh = files.slice(0, Math.max(room, 0))
      const poses = nextPoses(fresh.length, [...taken, ...current.map((item) => item.pose)])
      const added = fresh.map((file, index) => {
        const url = URL.createObjectURL(file)
        urls.current.push(url)
        return { key: `${file.name}-${file.size}-${Math.random()}`, file, url, pose: poses[index] }
      })
      return [...current, ...added]
    })
  }
  function remove(key: string) {
    setPicked((current) => current.filter((item) => item.key !== key))
  }
  function setPose(key: string, pose: Pose) {
    setPicked((current) => current.map((item) => (item.key === key ? { ...item, pose } : item)))
  }
  return { picked, add, remove, setPose, clear: () => setPicked([]) }
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const user = useUser()
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const today = todayIn(user.timezone)
  const { picked, add, remove, setPose } = usePicked()
  const [takenOn, setTakenOn] = useState(today)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const upload = useMutation({
    mutationFn: async () => {
      if (!picked.length) throw new Error('Выберите фото')
      for (const [index, item] of picked.entries())
        await bodyApi.uploadPhoto({
          file: item.file,
          taken_on: takenOn || undefined,
          pose: item.pose,
          note: index === 0 ? note.trim() || undefined : undefined,
        })
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success(picked.length > 1 ? 'Фото сохранены' : 'Фото сохранено')
      onDone()
    },
    onError: async (e) => {
      setError(e.message)
      await invalidateBody(client)
    },
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
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {picked.map((item, index) => (
          <div key={item.key} className="flex flex-col gap-1.5">
            <div className="relative">
              <img
                src={item.url}
                alt={`Фото ${index + 1}`}
                className="aspect-[3/4] w-full rounded-[14px] object-cover"
              />
              <button
                type="button"
                className="absolute top-1.5 right-1.5 grid size-8 place-items-center rounded-full bg-black/55 text-white"
                onClick={() => remove(item.key)}
                aria-label={`Убрать фото ${index + 1}`}
              >
                <X className="size-4" />
              </button>
            </div>
            <PoseSelect
              value={item.pose}
              onChange={(pose) => setPose(item.key, pose)}
              label={`Ракурс фото ${index + 1}`}
            />
          </div>
        ))}
        {picked.length < MAX_FILES && (
          <button
            type="button"
            onClick={() => input.current?.click()}
            className={cn(
              'grid place-items-center rounded-[14px] border border-dashed bg-muted text-muted-foreground',
              picked.length ? 'aspect-[3/4]' : 'col-span-full aspect-[16/9]',
            )}
          >
            <span className="flex flex-col items-center gap-2 text-sm">
              <ImagePlus className="size-7" />
              {picked.length ? 'Еще фото' : 'Выбрать фото: спереди, сбоку, сзади'}
            </span>
          </button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES}
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          add(Array.from(event.target.files ?? []), [])
          event.target.value = ''
        }}
      />
      <div className="flex flex-col gap-2">
        <Label htmlFor="entry-date">Дата</Label>
        <Input
          id="entry-date"
          type="date"
          value={takenOn}
          max={today}
          onChange={(event) => setTakenOn(event.target.value)}
          className="sm:w-56"
        />
        <p className="text-xs text-muted-foreground">
          Если за этот день уже есть запись, фото добавятся в нее.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="entry-note">Заметка</Label>
        <Textarea
          id="entry-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
          rows={2}
          placeholder="Например, утром натощак"
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={upload.isPending || !picked.length}>
        {upload.isPending ? 'Загружаем…' : 'Сохранить запись'}
      </Button>
    </form>
  )
}

function EntryForm({
  entry,
  version,
  onClose,
}: {
  entry: ProgressEntry
  version: string
  onClose: () => void
}) {
  const user = useUser()
  const client = useQueryClient()
  const today = todayIn(user.timezone)
  const input = useRef<HTMLInputElement>(null)
  const [takenOn, setTakenOn] = useState(entry.taken_on)
  const [note, setNote] = useState(entry.note ?? '')
  const [viewing, setViewing] = useState<number | null>(null)
  const [removingPhoto, setRemovingPhoto] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const dirty = takenOn !== entry.taken_on || note !== (entry.note ?? '')

  const save = useMutation({
    mutationFn: () =>
      bodyApi.updateEntry(entry.id, { taken_on: takenOn, note: note.trim() || null }),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Запись сохранена')
      onClose()
    },
  })
  const pose = useMutation({
    mutationFn: ({ id, value }: { id: number; value: Pose }) =>
      bodyApi.updatePhoto(id, { pose: value }),
    onSuccess: () => invalidateBody(client),
  })
  const addPhotos = useMutation({
    mutationFn: async (files: File[]) => {
      const room = MAX_FILES - entry.photos.length
      const chosen = files.slice(0, Math.max(room, 0))
      const poses = nextPoses(
        chosen.length,
        entry.photos.map((photo) => photo.pose),
      )
      for (const [index, file] of chosen.entries())
        await bodyApi.uploadPhoto({ file, taken_on: entry.taken_on, pose: poses[index] })
    },
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Фото добавлено')
    },
    onError: () => invalidateBody(client),
  })
  const removePhoto = useMutation({
    mutationFn: (id: number) => bodyApi.removePhoto(id),
    onSuccess: async () => {
      await invalidateBody(client)
      if (entry.photos.length === 1) onClose()
    },
    onError: () => invalidateBody(client),
    meta: { silent: true },
  })
  const remove = useMutation({
    mutationFn: () => bodyApi.removeEntry(entry.id),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Запись удалена')
      onClose()
    },
    onError: () => invalidateBody(client),
    meta: { silent: true },
  })

  const ids = entry.photos.map((photo) => photo.media_id)
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {entry.photos.map((photo, index) => (
          <div key={photo.id} className="flex flex-col gap-1.5">
            <div className="relative">
              <button
                type="button"
                className="block w-full overflow-hidden rounded-[14px]"
                onClick={() => setViewing(index)}
                aria-label={`Открыть: ${poseLabel(photo.pose)}`}
              >
                <Photo
                  id={photo.media_id}
                  alt={poseLabel(photo.pose)}
                  className="aspect-[3/4] w-full"
                  version={version}
                  eager
                />
              </button>
              <button
                type="button"
                className="absolute top-1.5 right-1.5 grid size-8 place-items-center rounded-full bg-black/55 text-white"
                onClick={() => setRemovingPhoto(photo.id)}
                aria-label={`Удалить фото: ${poseLabel(photo.pose)}`}
              >
                <Trash2 className="size-4" />
              </button>
            </div>
            <PoseSelect
              value={photo.pose}
              onChange={(value) => pose.mutate({ id: photo.id, value })}
              label={`Ракурс фото ${index + 1}`}
              disabled={pose.isPending}
            />
          </div>
        ))}
      </div>
      {entry.photos.length < MAX_FILES && (
        <Button
          type="button"
          variant="outline"
          className="self-start"
          onClick={() => input.current?.click()}
          disabled={addPhotos.isPending}
        >
          <ImagePlus />
          {addPhotos.isPending ? 'Загрузка…' : 'Добавить фото'}
        </Button>
      )}
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES}
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          event.target.value = ''
          if (files.length) addPhotos.mutate(files)
        }}
      />
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-entry-date">Дата</Label>
        <Input
          id="edit-entry-date"
          type="date"
          value={takenOn}
          max={today}
          onChange={(event) => setTakenOn(event.target.value)}
          required
          className="sm:w-56"
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-entry-note">Заметка</Label>
        <Textarea
          id="edit-entry-note"
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
          Удалить запись
        </Button>
        <Button type="submit" disabled={!dirty || save.isPending}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </div>
      <Lightbox
        ids={ids}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title="Фото прогресса"
        version={version}
      />
      <ConfirmDialog
        open={removingPhoto !== null}
        onOpenChange={(value) => !value && setRemovingPhoto(null)}
        title="Удалить это фото?"
        description="Фото удалится из записи и хранилища."
        onConfirm={() => removePhoto.mutateAsync(removingPhoto!)}
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Удалить запись?"
        description={`Удалятся все фото за ${formatDay(entry.taken_on, 'd MMMM')} без возможности восстановления.`}
        onConfirm={() => remove.mutateAsync()}
      />
    </form>
  )
}
