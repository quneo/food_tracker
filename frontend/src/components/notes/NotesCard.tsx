import { useQuery } from '@tanstack/react-query'
import { NotebookPen, PencilLine, Plus, ScanLine } from 'lucide-react'
import { notesApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { useRecordParam } from '@/components/record/RecordSheet'
import { cap } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useNoteParam } from './NoteSheet'
import type { Note } from '@/types'

/** Food weighed in advance: the ones whose meal has come are on top, ready to log. */
export function NotesCard({ className }: { className?: string }) {
  const notes = useQuery({
    queryKey: keys.notes,
    queryFn: ({ signal }) => notesApi.list({ signal }),
    refetchInterval: 5 * 60_000,
  })
  const { open } = useNoteParam()
  const waiting = notes.data ?? []
  if (!notes.data) return null
  if (!waiting.length)
    return (
      <button
        type="button"
        onClick={() => open()}
        className={cn(
          'glass flex min-h-14 items-center gap-3 rounded-[20px] px-4 py-3 text-left text-sm text-muted-foreground transition-colors hover:text-foreground',
          className,
        )}
      >
        <NotebookPen className="size-5 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 flex-1">
          Взвесили еду заранее? Запишите граммы, они дождутся нужного приема пищи.
        </span>
        <Plus className="size-5 shrink-0" aria-hidden="true" />
      </button>
    )
  return (
    <section
      className={cn('glass flex flex-col gap-3 rounded-[24px] p-4', className)}
      aria-label="Заметки о взвешивании"
    >
      <div className="flex items-center justify-between gap-2 pl-1">
        <h2 className="section-title">Заметки</h2>
        <Button variant="ghost" size="sm" onClick={() => open()}>
          <Plus />
          Заметка
        </Button>
      </div>
      <ul className="flex flex-col gap-2">
        {waiting.map((note) => (
          <NoteItem key={note.id} note={note} />
        ))}
      </ul>
    </section>
  )
}

function NoteItem({ note }: { note: Note }) {
  const record = useRecordParam()
  const { open } = useNoteParam()
  return (
    <li
      className={cn(
        'flex flex-col gap-2 rounded-[18px] border p-3',
        note.due ? 'border-primary/40 bg-lime-soft' : 'bg-card/60',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium">
          {cap(note.label)}
          {note.due && <span className="ml-2 text-xs font-normal text-primary">пора</span>}
        </p>
        <button
          type="button"
          onClick={() => open(note.id)}
          className="-m-1 grid size-8 shrink-0 place-items-center rounded-full text-muted-foreground hover:text-foreground"
          aria-label="Изменить заметку"
        >
          <PencilLine className="size-4" />
        </button>
      </div>
      <p className="text-[15px] leading-snug whitespace-pre-line">{note.text}</p>
      <Button
        size="sm"
        variant={note.due ? 'default' : 'outline'}
        className="self-start"
        onClick={() => record.open('photo', { note })}
      >
        <ScanLine />
        Записать по заметке
      </Button>
    </li>
  )
}
