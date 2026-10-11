import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BellRing,
  Camera,
  MessageSquareText,
  Pencil,
  Plus,
  Scale,
  Trash2,
  Utensils,
} from 'lucide-react'
import { toast } from 'sonner'
import { remindersApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { REMINDER_KINDS, WEEKDAYS, reminderLabel } from '@/lib/labels'
import { dateTimeLabel, todayIn } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Reminder, ReminderIn, ReminderKind } from '@/types'

const ICONS: Record<ReminderKind, typeof BellRing> = {
  meal: Utensils,
  weight: Scale,
  photo: Camera,
  custom: MessageSquareText,
}

function schedule(days: number[]) {
  const key = [...days].sort((a, b) => a - b).join(',')
  if (key === '1,2,3,4,5,6,7') return 'каждый день'
  if (key === '1,2,3,4,5') return 'по будням'
  if (key === '6,7') return 'по выходным'
  return WEEKDAYS.filter((day) => days.includes(day.value))
    .map((day) => day.short.toLowerCase())
    .join(', ')
}

const toInput = (reminder: Reminder): ReminderIn => ({
  kind: reminder.kind,
  time: reminder.time,
  days: reminder.days,
  text: reminder.text,
  enabled: reminder.enabled,
  smart_skip: reminder.smart_skip,
})

export function RemindersSection() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const client = useQueryClient()
  const [editing, setEditing] = useState<Reminder | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Reminder | null>(null)
  const reminders = useQuery({
    queryKey: keys.reminders,
    queryFn: ({ signal }) => remindersApi.list({ signal }),
  })
  const toggle = useMutation({
    mutationFn: (reminder: Reminder) =>
      remindersApi.update(reminder.id, { ...toInput(reminder), enabled: !reminder.enabled }),
    onSuccess: (saved) => {
      client.setQueryData<Reminder[]>(keys.reminders, (list) =>
        list?.map((item) => (item.id === saved.id ? saved : item)),
      )
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) => remindersApi.remove(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.reminders })
      toast.success('Напоминание удалено')
    },
    meta: { silent: true },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Напоминания</CardTitle>
        <CardDescription>Приходят в чат с ботом по вашему часовому поясу.</CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
            <Plus />
            Добавить
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {reminders.isPending ? (
          <BlockSkeleton rows={3} />
        ) : reminders.isError ? (
          <ErrorState error={reminders.error} retry={() => reminders.refetch()} />
        ) : !reminders.data.length ? (
          <EmptyState
            icon={BellRing}
            title="Напоминаний нет"
            description="Добавьте, например, вечернее «записать питание»."
          />
        ) : (
          <ul className="row-list -mx-2">
            {reminders.data.map((reminder) => {
              const Icon = ICONS[reminder.kind]
              const title =
                reminder.kind === 'custom'
                  ? reminder.text || 'Свое напоминание'
                  : reminderLabel(reminder.kind)
              return (
                <li key={reminder.id} className="flex items-center gap-3 px-2 py-3">
                  <span
                    className={cn(
                      'grid size-10 shrink-0 place-items-center rounded-xl',
                      reminder.enabled
                        ? 'bg-accent text-accent-foreground'
                        : 'bg-muted text-muted-foreground',
                    )}
                    aria-hidden="true"
                  >
                    <Icon className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        'truncate font-medium',
                        !reminder.enabled && 'text-muted-foreground',
                      )}
                    >
                      {title}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      <span className="tabular">{reminder.time}</span> · {schedule(reminder.days)}
                    </p>
                    {reminder.enabled && reminder.next_run_at && (
                      <p className="text-xs text-muted-foreground">
                        Следующее: {dateTimeLabel(reminder.next_run_at, today)}
                      </p>
                    )}
                  </div>
                  <Switch
                    checked={reminder.enabled}
                    onCheckedChange={() => toggle.mutate(reminder)}
                    disabled={toggle.isPending}
                    aria-label={`${title}: ${reminder.enabled ? 'выключить' : 'включить'}`}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setEditing(reminder)}
                    aria-label={`Изменить: ${title}`}
                  >
                    <Pencil />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
      <ResponsiveSheet
        open={editing !== undefined}
        onOpenChange={(value) => !value && setEditing(undefined)}
        title={editing ? 'Напоминание' : 'Новое напоминание'}
      >
        {editing !== undefined && (
          <ReminderForm
            reminder={editing}
            onDone={() => setEditing(undefined)}
            onDelete={editing ? () => setDeleting(editing) : undefined}
          />
        )}
      </ResponsiveSheet>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(value) => !value && setDeleting(null)}
        title="Удалить напоминание?"
        onConfirm={async () => {
          await remove.mutateAsync(deleting!.id)
          setEditing(undefined)
        }}
      />
    </Card>
  )
}

const PRESETS = [
  { label: 'Каждый день', days: [1, 2, 3, 4, 5, 6, 7] },
  { label: 'Будни', days: [1, 2, 3, 4, 5] },
  { label: 'Выходные', days: [6, 7] },
]

function ReminderForm({
  reminder,
  onDone,
  onDelete,
}: {
  reminder: Reminder | null
  onDone: () => void
  onDelete?: () => void
}) {
  const client = useQueryClient()
  const [form, setForm] = useState<ReminderIn>(
    reminder
      ? toInput(reminder)
      : {
          kind: 'meal',
          time: '21:00',
          days: [1, 2, 3, 4, 5, 6, 7],
          text: null,
          enabled: true,
          smart_skip: true,
        },
  )
  const [error, setError] = useState('')
  const set = <K extends keyof ReminderIn>(field: K, value: ReminderIn[K]) =>
    setForm((current) => ({ ...current, [field]: value }))
  const save = useMutation({
    mutationFn: () => {
      if (!/^\d{2}:\d{2}$/.test(form.time)) throw new Error('Укажите время')
      if (!form.days.length) throw new Error('Выберите хотя бы один день')
      if (form.kind === 'custom' && !form.text?.trim())
        throw new Error('Напишите текст напоминания')
      const data = { ...form, text: form.kind === 'custom' ? form.text?.trim() || null : null }
      return reminder ? remindersApi.update(reminder.id, data) : remindersApi.create(data)
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.reminders })
      toast.success('Напоминание сохранено')
      onDone()
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div className="flex flex-col gap-2">
        <span id="reminder-kind" className="text-sm font-medium">
          О чем напомнить
        </span>
        <div className="chips" role="radiogroup" aria-labelledby="reminder-kind">
          {REMINDER_KINDS.map((kind) => (
            <button
              key={kind.value}
              type="button"
              role="radio"
              aria-checked={form.kind === kind.value}
              data-state={form.kind === kind.value ? 'on' : 'off'}
              className="chip"
              onClick={() => set('kind', kind.value)}
            >
              {kind.label}
            </button>
          ))}
        </div>
      </div>
      {form.kind === 'custom' && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="reminder-text">Текст</Label>
          <Input
            id="reminder-text"
            value={form.text ?? ''}
            onChange={(event) => set('text', event.target.value)}
            maxLength={300}
            placeholder="Например, выпить воды"
            required
          />
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="reminder-time">Время</Label>
        <Input
          id="reminder-time"
          type="time"
          value={form.time}
          onChange={(event) => set('time', event.target.value)}
          required
          className="w-36"
        />
      </div>
      <div className="flex flex-col gap-2">
        <span id="reminder-days" className="text-sm font-medium">
          Дни
        </span>
        <div className="grid grid-cols-7 gap-1.5" role="group" aria-labelledby="reminder-days">
          {WEEKDAYS.map((day) => {
            const on = form.days.includes(day.value)
            return (
              <button
                key={day.value}
                type="button"
                aria-pressed={on}
                aria-label={day.label}
                className={cn(
                  'grid h-11 place-items-center rounded-xl border text-sm transition-colors',
                  on
                    ? 'border-primary bg-accent font-medium text-accent-foreground'
                    : 'hover:bg-muted',
                )}
                onClick={() =>
                  set(
                    'days',
                    on
                      ? form.days.filter((value) => value !== day.value)
                      : [...form.days, day.value].sort((a, b) => a - b),
                  )
                }
              >
                {day.short}
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <Button
              key={preset.label}
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => set('days', preset.days)}
            >
              {preset.label}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex items-start justify-between gap-4">
        <Label htmlFor="reminder-skip" className="flex flex-col items-start gap-1 font-normal">
          <span className="font-medium">Не напоминать, если уже сделано</span>
          <span className="text-sm text-muted-foreground">
            Например, если вес сегодня уже записан
          </span>
        </Label>
        <Switch
          id="reminder-skip"
          checked={form.smart_skip}
          onCheckedChange={(value) => set('smart_skip', value)}
          className="mt-1"
        />
      </div>
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="reminder-enabled" className="font-medium">
          Включено
        </Label>
        <Switch
          id="reminder-enabled"
          checked={form.enabled}
          onCheckedChange={(value) => set('enabled', value)}
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {onDelete ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 />
            Удалить
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </div>
    </form>
  )
}
