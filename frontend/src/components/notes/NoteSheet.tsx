import { useCallback, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { notesApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import type { MealType, Note } from '@/types'

export const NOTE_TARGETS: { value: MealType | null; label: string }[] = [
  { value: null, label: 'Ближайшие 3 часа' },
  { value: 'breakfast', label: 'Завтрак' },
  { value: 'lunch', label: 'Обед' },
  { value: 'dinner', label: 'Ужин' },
  { value: 'snack', label: 'Перекус' },
]

/** The note form lives in the address (?note=new or ?note=12): the back button closes it.
 * A new note may start with text, passed in the navigation state. */
export function useNoteParam() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const raw = params.get('note')
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null
  const creating = raw === 'new'
  const text = (location.state as { noteText?: string } | null)?.noteText ?? ''

  const open = useCallback(
    (note: number | 'new' = 'new', prefill = '', replace = false) => {
      const next = new URLSearchParams(location.search)
      next.delete('record')
      next.set('note', String(note))
      navigate(
        { search: next.toString() },
        { replace, state: { noteOpened: !replace, noteText: prefill } },
      )
    },
    [location.search, navigate],
  )
  const close = useCallback(() => {
    if ((location.state as { noteOpened?: boolean } | null)?.noteOpened) {
      navigate(-1)
      return
    }
    const next = new URLSearchParams(location.search)
    next.delete('note')
    navigate({ search: next.toString() }, { replace: true })
  }, [location.search, location.state, navigate])
  return { id, creating, text, open, close }
}

export function NoteSheetHost() {
  const { id, creating, text, close } = useNoteParam()
  const list = useQuery({
    queryKey: keys.notes,
    queryFn: ({ signal }) => notesApi.list({ signal }),
    enabled: id !== null,
  })
  const note = id !== null ? list.data?.find((item) => item.id === id) : undefined
  const open = creating || note !== undefined
  return (
    <ResponsiveSheet
      open={open}
      onOpenChange={(value) => !value && close()}
      title={note ? 'Заметка' : 'Новая заметка'}
      description="Взвесили сейчас, едите потом: граммы подождут нужного приема пищи."
    >
      {open && <NoteForm key={note?.id ?? 'new'} note={note} prefill={text} onDone={close} />}
    </ResponsiveSheet>
  )
}

function NoteForm({ note, prefill, onDone }: { note?: Note; prefill: string; onDone: () => void }) {
  const client = useQueryClient()
  const [text, setText] = useState(note?.text ?? prefill)
  const [target, setTarget] = useState<MealType | null>(note ? note.meal_type : null)
  const save = useMutation({
    mutationFn: () =>
      note
        ? notesApi.update(note.id, { text, meal_type: target })
        : notesApi.create({ text, meal_type: target }),
    onSuccess: (saved) => {
      toast.success(note ? 'Заметка обновлена' : `Заметка ${saved.label}`)
      onDone()
      return client.invalidateQueries({ queryKey: keys.notes })
    },
  })
  const remove = useMutation({
    mutationFn: () => notesApi.remove(note!.id),
    onSuccess: () => {
      toast.success('Заметка удалена')
      onDone()
      return client.invalidateQueries({ queryKey: keys.notes })
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (text.trim()) save.mutate()
      }}
    >
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">Что взвесили</span>
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={5}
          maxLength={1000}
          autoFocus={!note}
          placeholder={'130 грудка\n150 рис басмати\n200 перец'}
        />
      </label>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">Когда съедите</legend>
        <div className="chips">
          {NOTE_TARGETS.map((item) => (
            <button
              key={item.label}
              type="button"
              className="chip"
              aria-pressed={target === item.value}
              onClick={() => setTarget(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          {target === null
            ? 'Сгорит через 3 часа, если не учесть.'
            : 'Ближайший такой прием: заметка появится к его времени и сгорит после.'}
        </p>
      </fieldset>
      <div className="flex gap-2">
        <Button
          type="submit"
          size="lg"
          className="min-h-12 flex-1"
          disabled={!text.trim() || save.isPending}
        >
          <Check />
          Сохранить
        </Button>
        {note && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-12 text-muted-foreground hover:text-destructive"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            aria-label="Удалить заметку"
          >
            <Trash2 />
          </Button>
        )}
      </div>
    </form>
  )
}
