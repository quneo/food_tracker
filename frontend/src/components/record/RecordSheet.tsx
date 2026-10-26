import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Camera,
  Check,
  ImagePlus,
  NotebookPen,
  PencilLine,
  ScanLine,
  Sparkles,
  Tag,
  Trash2,
  Utensils,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { assistantApi, mealsApi, notesApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { MacroLine } from '@/components/meals/MealBits'
import { MealEditor } from '@/components/meals/MealEditor'
import { PHOTO_TYPES } from '@/components/meals/MealPhotos'
import { Photo } from '@/components/shared/Photo'
import { shrinkPhoto } from '@/lib/images'
import { itemWeight, num } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useNoteParam } from '@/components/notes/NoteSheet'
import { ProductPick } from './ProductPick'
import type { AssistantJob, Meal, Note, RecordMode } from '@/types'

export type RecordTab = 'photo' | 'label' | 'product' | 'manual'
const TABS: { value: RecordTab; label: string; icon: typeof Camera }[] = [
  { value: 'photo', label: 'Еда', icon: ScanLine },
  { value: 'label', label: 'Этикетка', icon: Tag },
  { value: 'product', label: 'Мои продукты', icon: Utensils },
  { value: 'manual', label: 'Вручную', icon: PencilLine },
]
const MAX_PHOTOS = 6

interface Job {
  id: number
  /** The first photo, shown under the scanning line while the assistant counts. */
  cover: string | null
}

/** The open form lives in the address (?record=photo), so the back button closes it. */
export function useRecordParam() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const raw = params.get('record')
  const tab = TABS.some((item) => item.value === raw) ? (raw as RecordTab) : null

  /** `note`: logging the food of a weigh note, its grams already in the text. */
  const open = useCallback(
    (value: RecordTab = 'photo', options: { note?: Note } = {}) => {
      const next = new URLSearchParams(location.search)
      next.set('record', value)
      navigate({ search: next.toString() }, { state: { recordOpened: true, note: options.note } })
    },
    [location.search, navigate],
  )
  const note = (location.state as { note?: Note } | null)?.note ?? null
  const setTab = useCallback(
    (value: RecordTab) => {
      const next = new URLSearchParams(location.search)
      next.set('record', value)
      navigate({ search: next.toString() }, { replace: true, state: location.state })
    },
    [location.search, location.state, navigate],
  )
  const close = useCallback(() => {
    if ((location.state as { recordOpened?: boolean } | null)?.recordOpened) {
      navigate(-1)
      return
    }
    const next = new URLSearchParams(location.search)
    next.delete('record')
    navigate({ search: next.toString() }, { replace: true })
  }, [location.search, location.state, navigate])
  /** From the result straight to fixing the meal, without the form in history. */
  const editMeal = useCallback(
    (id: number) => {
      const next = new URLSearchParams(location.search)
      next.delete('record')
      next.set('meal', String(id))
      next.set('edit', '1')
      navigate({ search: next.toString() }, { replace: true })
    },
    [location.search, navigate],
  )
  return { tab, open, setTab, close, editMeal, note }
}

export function RecordSheetHost() {
  const { tab, setTab, close, editMeal, note } = useRecordParam()
  // The job outlives a closed sheet: reopening shows how it went.
  const [job, setJob] = useState<Job | null>(null)
  const changeJob = useCallback((next: Job | null) => {
    setJob((current) => {
      if (current?.cover) URL.revokeObjectURL(current.cover)
      return next
    })
  }, [])
  return (
    <ResponsiveSheet
      open={tab !== null}
      onOpenChange={(value) => !value && close()}
      title="Записать прием пищи"
      wide
    >
      {tab && (
        <RecordFlow
          tab={tab}
          onTab={setTab}
          onClose={close}
          onEdit={editMeal}
          job={job}
          onJob={changeJob}
          note={note}
        />
      )}
    </ResponsiveSheet>
  )
}

function RecordFlow({
  tab,
  onTab,
  onClose,
  onEdit,
  job,
  onJob,
  note,
}: {
  tab: RecordTab
  onTab: (tab: RecordTab) => void
  onClose: () => void
  onEdit: (id: number) => void
  job: Job | null
  onJob: (job: Job | null) => void
  note: Note | null
}) {
  if (job)
    return (
      <JobView
        id={job.id}
        cover={job.cover}
        onAgain={() => onJob(null)}
        onClose={onClose}
        onEdit={onEdit}
      />
    )
  return (
    <div className="flex flex-col gap-5">
      <div className="mode-tabs" role="tablist" aria-label="Как записать">
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            className="mode-tab"
            aria-selected={tab === item.value}
            onClick={() => onTab(item.value)}
          >
            <item.icon aria-hidden="true" />
            {item.label}
          </button>
        ))}
      </div>
      {tab === 'photo' || tab === 'label' ? (
        <PhotoCompose
          key={tab}
          mode={tab === 'label' ? 'label' : 'food'}
          onJob={onJob}
          note={tab === 'photo' ? note : null}
        />
      ) : tab === 'product' ? (
        <ProductPick onDone={onClose} />
      ) : (
        <MealEditor
          onDone={onClose}
          onCreated={() => toast.success('Записано в дневник')}
          onCancel={onClose}
        />
      )}
    </div>
  )
}

function PhotoCompose({
  mode,
  onJob,
  note,
}: {
  mode: RecordMode
  onJob: (job: Job) => void
  note: Note | null
}) {
  const client = useQueryClient()
  const camera = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)
  const later = useNoteParam()
  const [files, setFiles] = useState<File[]>([])
  const [text, setText] = useState(note?.text ?? '')
  // The weigh note this meal is made from: it is used up once the meal is recorded.
  const [noteId, setNoteId] = useState<number | null>(note?.id ?? null)
  const notes = useQuery({
    queryKey: keys.notes,
    queryFn: ({ signal }) => notesApi.list({ signal }),
    enabled: mode === 'food',
  })
  const due = (notes.data ?? []).filter((item) => item.due && item.id !== noteId)
  const take = (item: Note) => {
    setNoteId(item.id)
    setText((current) => (current.trim() ? `${item.text}\n${current}` : item.text))
  }
  const [over, setOver] = useState(false)
  const previews = useMemo(() => files.map((file) => URL.createObjectURL(file)), [files])
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews])

  const add = (list: FileList | File[] | null) => {
    const images = Array.from(list ?? []).filter((file) => file.type.startsWith('image/'))
    if (images.length) setFiles((current) => [...current, ...images].slice(0, MAX_PHOTOS))
  }
  const send = useMutation({
    mutationFn: async () =>
      assistantApi.logMeal({
        text,
        mode,
        noteId,
        photos: await Promise.all(files.map((file) => shrinkPhoto(file))),
      }),
    onSuccess: (job) => {
      client.setQueryData(keys.assistantJob(job.id), job)
      onJob({ id: job.id, cover: files[0] ? URL.createObjectURL(files[0]) : null })
    },
  })
  const label = mode === 'label'
  const ready = files.length > 0 || (!label && text.trim().length > 0)

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (ready) send.mutate()
      }}
    >
      {due.length > 0 && (
        <div className="flex flex-col gap-2">
          {due.map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-3 rounded-[18px] border border-primary/40 bg-lime-soft p-3"
            >
              <span className="min-w-0 flex-1 text-sm">
                <span className="block font-medium">Заметка {item.label}</span>
                <span className="block whitespace-pre-line text-muted-foreground">{item.text}</span>
              </span>
              <Button type="button" size="sm" onClick={() => take(item)}>
                Взять
              </Button>
            </div>
          ))}
        </div>
      )}
      {files.length === 0 ? (
        <div
          className={cn('drop-zone', over && 'is-over')}
          onDragOver={(event) => {
            event.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault()
            setOver(false)
            add(event.dataTransfer.files)
          }}
        >
          {label ? (
            <Tag className="size-8" aria-hidden="true" />
          ) : (
            <ScanLine className="size-8" aria-hidden="true" />
          )}
          <p className="max-w-[30ch] text-sm">
            {label
              ? 'Сфотографируйте этикетку с пищевой ценностью, ассистент перепишет цифры'
              : 'Сфотографируйте тарелку целиком, ассистент разберет, что на ней, и посчитает'}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <Button type="button" onClick={() => camera.current?.click()}>
              <Camera />
              Сфотографировать
            </Button>
            <Button type="button" variant="outline" onClick={() => gallery.current?.click()}>
              <ImagePlus />
              Из галереи
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {previews.map((url, index) => (
            <div key={url} className="relative">
              <img
                src={url}
                alt={`Фото ${index + 1}`}
                className="aspect-square w-full rounded-[16px] object-cover"
              />
              <button
                type="button"
                className="absolute top-1.5 right-1.5 grid size-8 place-items-center rounded-full bg-black/55 text-white"
                onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                aria-label={`Убрать фото ${index + 1}`}
              >
                <X className="size-4" />
              </button>
            </div>
          ))}
          {files.length < MAX_PHOTOS && (
            <button
              type="button"
              className="flex aspect-square flex-col items-center justify-center gap-1 rounded-[16px] border-[1.5px] border-dashed border-input text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              onClick={() => gallery.current?.click()}
            >
              <ImagePlus className="size-5" aria-hidden="true" />
              Еще фото
            </button>
          )}
        </div>
      )}
      <label className="flex flex-col gap-2">
        <span className="flex items-center justify-between gap-2 text-sm font-medium">
          {label ? 'Сколько съели' : files.length ? 'Подсказка ассистенту' : 'Или опишите словами'}
          {noteId !== null && (
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs text-accent-foreground"
              onClick={() => setNoteId(null)}
              aria-label="Записать не по заметке"
            >
              По заметке
              <X className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </span>
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={2}
          maxLength={2000}
          placeholder={
            label
              ? '«половину пачки», «2 печенья», «150 г»'
              : files.length
                ? '«без масла», «съел половину», «соус песто»'
                : '«гречка 200 г и котлета», «латте 400 мл»'
          }
        />
      </label>
      <Button type="submit" size="lg" className="min-h-12" disabled={!ready || send.isPending}>
        <Sparkles />
        {send.isPending ? 'Отправляю…' : 'Посчитать'}
      </Button>
      {!label && noteId === null && files.length === 0 && text.trim() && (
        // Weighed now, eaten later: the grams go to a note instead.
        <Button type="button" variant="ghost" onClick={() => later.open('new', text, true)}>
          <NotebookPen />
          Съем позже — сохранить заметкой
        </Button>
      )}
      <input
        ref={camera}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          add(event.target.files)
          event.target.value = ''
        }}
      />
      <input
        ref={gallery}
        type="file"
        accept={`${PHOTO_TYPES},image/heic,image/heif`}
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          add(event.target.files)
          event.target.value = ''
        }}
      />
    </form>
  )
}

function JobView({
  id,
  cover,
  onAgain,
  onClose,
  onEdit,
}: {
  id: number
  cover: string | null
  onAgain: () => void
  onClose: () => void
  onEdit: (id: number) => void
}) {
  const client = useQueryClient()
  const job = useQuery({
    queryKey: keys.assistantJob(id),
    queryFn: ({ signal }) => assistantApi.job(id, { signal }),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'failed' ? false : 1500
    },
  })
  const status = job.data?.status
  useEffect(() => {
    if (status === 'done') void invalidateMeals(client)
  }, [status, client])

  if (job.isError) return <Failure text={job.error.message} onAgain={onAgain} onClose={onClose} />
  if (!job.data || status === 'queued' || status === 'running')
    return <Counting cover={cover} onClose={onClose} />
  if (status === 'failed')
    return (
      <Failure
        text={job.data.error ?? 'Не получилось посчитать. Попробуйте еще раз'}
        onAgain={onAgain}
        onClose={onClose}
      />
    )
  return <Results job={job.data} onAgain={onAgain} onClose={onClose} onEdit={onEdit} />
}

function Counting({ cover, onClose }: { cover: string | null; onClose: () => void }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="flex flex-col gap-4" aria-live="polite">
      {cover ? (
        <div className="scanner aspect-[4/3]">
          <img src={cover} alt="" className="size-full object-cover" />
        </div>
      ) : (
        <div className="scanner grid aspect-[4/3] place-items-center bg-linear-to-br from-lime-soft to-accent">
          <Utensils className="size-10 text-accent-foreground opacity-60" aria-hidden="true" />
        </div>
      )}
      <div className="flex items-baseline justify-between gap-3">
        <p className="section-title">Считаю калории</p>
        <span className="text-sm text-muted-foreground tabular">
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
        </span>
      </div>
      <p className="text-sm text-muted-foreground">
        Разбираю, что на фото, и прикидываю вес каждой части. Обычно это до минуты. Окно можно
        закрыть: черновик появится в дневнике.
      </p>
      <Button variant="outline" onClick={onClose}>
        Свернуть
      </Button>
    </div>
  )
}

function Failure({
  text,
  onAgain,
  onClose,
}: {
  text: string
  onAgain: () => void
  onClose: () => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-[16px] bg-warning-soft p-4 text-sm text-warning">{text}</p>
      <div className="flex gap-2">
        <Button onClick={onAgain}>Попробовать еще раз</Button>
        <Button variant="ghost" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  )
}

function Results({
  job,
  onAgain,
  onClose,
  onEdit,
}: {
  job: AssistantJob
  onAgain: () => void
  onClose: () => void
  onEdit: (id: number) => void
}) {
  return (
    <div className="flex flex-col gap-4">
      {job.reply && <p className="text-[15px] leading-relaxed">{job.reply}</p>}
      {job.notes.map((note) => (
        <p key={note} className="rounded-[14px] bg-warning-soft px-3 py-2 text-sm text-warning">
          {note}
        </p>
      ))}
      {job.meals.length === 0 && !job.reply && (
        <p className="text-sm text-muted-foreground">
          Ассистент не нашел еды для записи. Попробуйте другое фото или опишите словами.
        </p>
      )}
      {job.meals.map((meal) => (
        <ResultMeal key={meal.id} id={meal.id} initial={meal} onEdit={onEdit} />
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={onAgain}>
          <ScanLine />
          Записать еще
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Готово
        </Button>
      </div>
    </div>
  )
}

/** A meal the assistant just counted: the numbers, its note, and what to do with it. */
function ResultMeal({
  id,
  initial,
  onEdit,
}: {
  id: number
  initial: Meal
  onEdit: (id: number) => void
}) {
  const client = useQueryClient()
  const meal = useQuery({
    queryKey: keys.meal(id),
    queryFn: ({ signal }) => mealsApi.get(id, { signal }),
    initialData: initial,
  })
  const confirm = useMutation({
    mutationFn: () => mealsApi.confirm(id),
    onSuccess: (value) => {
      client.setQueryData(keys.meal(id), value)
      toast.success('Сохранено в дневнике')
      return invalidateMeals(client)
    },
  })
  const remove = useMutation({
    mutationFn: () => mealsApi.remove(id),
    onSuccess: () => {
      toast.success('Черновик удален')
      client.removeQueries({ queryKey: keys.meal(id) })
      return invalidateMeals(client)
    },
  })
  if (meal.isError || remove.isSuccess) return null
  const value = meal.data
  const draft = value.status === 'draft'
  return (
    <article className="overflow-hidden rounded-[22px] border bg-card">
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          {value.photos[0] && (
            <Photo id={value.photos[0].id} alt="" className="size-12 shrink-0 rounded-[14px]" />
          )}
          <h3 className="min-w-0 flex-1 self-center font-semibold leading-snug">{value.title}</h3>
          <span className="serif-number shrink-0 text-2xl leading-none whitespace-nowrap">
            {num(value.kcal)} <span className="font-sans text-xs font-normal">ккал</span>
          </span>
        </div>
        <MacroLine value={value} className="text-[13px] text-muted-foreground" />
        <ul className="flex flex-col gap-1 text-sm">
          {value.items.map((item) => (
            <li key={item.id} className="flex justify-between gap-3">
              <span className="min-w-0">
                {item.name}{' '}
                <span className="whitespace-nowrap text-muted-foreground">{itemWeight(item)}</span>
              </span>
              <span className="shrink-0 tabular text-muted-foreground">{num(item.kcal)}</span>
            </li>
          ))}
        </ul>
        {value.ai_comment && (
          <p className="rounded-r-[12px] border-l-[3px] border-primary bg-accent/60 px-3 py-2 text-sm leading-snug">
            {value.ai_comment}
          </p>
        )}
      </div>
      <div className="grid grid-cols-[1fr_1fr_auto] gap-1 border-t p-2">
        {draft ? (
          <Button onClick={() => confirm.mutate()} disabled={confirm.isPending}>
            <Check />
            Сохранить
          </Button>
        ) : (
          <span className="flex items-center justify-center gap-1.5 text-sm font-medium text-primary">
            <Check className="size-4" aria-hidden="true" />В дневнике
          </span>
        )}
        <Button variant="outline" onClick={() => onEdit(id)}>
          <PencilLine />
          Исправить
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
          aria-label="Удалить запись"
        >
          <Trash2 />
        </Button>
      </div>
    </article>
  )
}
