import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, Pencil, Plus, Ruler, Scale, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { bodyApi, profileApi } from '@/api/endpoints'
import { invalidateBody, keys } from '@/api/keys'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { TrendLine, type TrendPoint } from '@/components/analytics/TrendLine'
import { MEASUREMENTS, measurement } from '@/lib/labels'
import {
  dateTimeLabel,
  formatDay,
  inputNumber,
  localInput,
  nowIn,
  num,
  parseNumber,
  signed,
  todayIn,
} from '@/lib/format'
import { cn } from '@/lib/utils'
import { WeightSheet } from './WeightEditor'
import type { Measurement, MeasurementKind, Weight } from '@/types'

const SOURCE: Record<string, string> = { bot: 'из бота', web: '' }

export function BodySection() {
  return (
    <div className="flex flex-col gap-4">
      <WeightBlock />
      <MeasurementsBlock />
    </div>
  )
}

function RowMenu({
  label,
  onEdit,
  onDelete,
}: {
  label: string
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Действия: ${label}`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onEdit}>
          <Pencil />
          Изменить
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onDelete} className="text-destructive focus:text-destructive">
          <Trash2 />
          Удалить
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function WeightBlock() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const client = useQueryClient()
  const [editing, setEditing] = useState<Weight | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Weight | null>(null)
  const [all, setAll] = useState(false)
  const weights = useQuery({
    queryKey: keys.weights,
    queryFn: ({ signal }) => bodyApi.weights({}, { signal }),
  })
  const profile = useQuery({
    queryKey: keys.profile,
    queryFn: ({ signal }) => profileApi.get({ signal }),
  })
  const remove = useMutation({
    mutationFn: (id: number) => bodyApi.removeWeight(id),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Взвешивание удалено')
    },
    meta: { silent: true },
  })

  const list = weights.data ?? []
  const points: TrendPoint[] = [...list].reverse().map((entry) => ({
    key: String(entry.id),
    label: formatDay(entry.measured_on, 'd.MM'),
    title: dateTimeLabel(entry.measured_at, today),
    value: entry.weight_kg,
  }))
  const shown = all ? list : list.slice(0, 8)
  const first = list[list.length - 1]
  const latest = list[0]
  return (
    <Card>
      <CardHeader>
        <CardTitle>Вес</CardTitle>
        <CardDescription>
          {latest && first && latest.id !== first.id
            ? `${num(first.weight_kg, 1)} → ${num(latest.weight_kg, 1)} кг (${signed(latest.weight_kg - first.weight_kg)}) с ${formatDay(first.measured_on, 'd MMM yyyy')}`
            : 'Все взвешивания'}
        </CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
            <Plus />
            Записать
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {weights.isPending ? (
          <BlockSkeleton rows={3} />
        ) : weights.isError ? (
          <ErrorState error={weights.error} retry={() => weights.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={Scale}
            title="Взвешиваний пока нет"
            description="Пришлите вес боту, например «72,4», или запишите здесь."
          />
        ) : (
          <div className="grid gap-4 min-[1180px]:grid-cols-[minmax(0,1fr)_300px] min-[1180px]:items-start">
            {points.length > 1 ? (
              <TrendLine
                points={points}
                unit="кг"
                name="Вес"
                target={profile.data?.target_weight_kg}
              />
            ) : (
              <span />
            )}
            <div className="flex flex-col gap-2 min-[1180px]:max-h-[420px] min-[1180px]:overflow-x-hidden min-[1180px]:overflow-y-auto">
              <ul className="row-list">
                {shown.map((entry) => (
                  <li key={entry.id} className="flex items-center gap-3 px-2 py-1.5">
                    <div className="min-w-0 flex-1">
                      <p className="serif-number tabular">{num(entry.weight_kg, 1)} кг</p>
                      <p className="truncate text-sm text-muted-foreground">
                        {dateTimeLabel(entry.measured_at, today)}
                        {SOURCE[entry.source] ? `, ${SOURCE[entry.source].toLowerCase()}` : ''}
                        {entry.note ? `. ${entry.note}` : ''}
                      </p>
                    </div>
                    <RowMenu
                      label={`${num(entry.weight_kg, 1)} кг`}
                      onEdit={() => setEditing(entry)}
                      onDelete={() => setDeleting(entry)}
                    />
                  </li>
                ))}
              </ul>
              {list.length > 8 && (
                <Button variant="ghost" className="self-center" onClick={() => setAll(!all)}>
                  {all ? 'Свернуть' : `Показать все (${list.length})`}
                </Button>
              )}
            </div>
          </div>
        )}
      </CardContent>
      <WeightSheet
        open={editing !== undefined}
        onOpenChange={(value) => !value && setEditing(undefined)}
        entry={editing}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(value) => !value && setDeleting(null)}
        title="Удалить взвешивание?"
        description={
          deleting
            ? `${num(deleting.weight_kg, 1)} кг, ${dateTimeLabel(deleting.measured_at)}`
            : undefined
        }
        onConfirm={() => remove.mutateAsync(deleting!.id)}
      />
    </Card>
  )
}

function MeasurementsBlock() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const client = useQueryClient()
  const [kind, setKind] = useState<MeasurementKind | null>(null)
  const [editing, setEditing] = useState<Measurement | null | undefined>(undefined)
  const [writing, setWriting] = useState(false)
  const [deleting, setDeleting] = useState<Measurement | null>(null)
  const entries = useQuery({
    queryKey: keys.measurements,
    queryFn: ({ signal }) => bodyApi.measurements({}, { signal }),
  })
  const remove = useMutation({
    mutationFn: (id: number) => bodyApi.removeMeasurement(id),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Замер удален')
    },
    meta: { silent: true },
  })

  const list = entries.data ?? []
  const kinds = MEASUREMENTS.map((item) => {
    const own = list.filter((entry) => entry.kind === item.value)
    return { ...item, entries: own }
  }).filter((item) => item.entries.length)
  const active = kinds.find((item) => item.value === kind) ?? kinds[0]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Замеры</CardTitle>
        <CardDescription>Объемы тела и процент жира</CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={() => setWriting(true)}>
            <Plus />
            Записать
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {entries.isPending ? (
          <BlockSkeleton rows={3} />
        ) : entries.isError ? (
          <ErrorState error={entries.error} retry={() => entries.refetch()} />
        ) : !kinds.length ? (
          <EmptyState
            icon={Ruler}
            title="Замеров пока нет"
            description="Талия, бедра, грудь и другие объемы — раз в 1–2 недели, утром."
          >
            <Button variant="outline" onClick={() => setWriting(true)}>
              <Ruler />
              Записать замеры
            </Button>
          </EmptyState>
        ) : (
          <>
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {kinds.map((item) => {
                const latest = item.entries[0]
                const previous = item.entries[1]
                const first = item.entries[item.entries.length - 1]
                const points: TrendPoint[] = [...item.entries].reverse().map((entry) => ({
                  key: String(entry.id),
                  label: formatDay(entry.measured_on, 'd.MM'),
                  title: formatDay(entry.measured_on, 'd MMMM yyyy'),
                  value: entry.value,
                }))
                return (
                  <li key={item.value}>
                    <button
                      type="button"
                      aria-pressed={active?.value === item.value}
                      onClick={() => setKind(item.value)}
                      className={cn(
                        'flex w-full flex-col gap-1 rounded-[14px] border p-3 text-left transition-colors hover:bg-muted',
                        active?.value === item.value && 'border-primary bg-accent hover:bg-accent',
                      )}
                    >
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-lg font-semibold tabular">
                        {num(latest.value, 1)}{' '}
                        <span className="text-sm font-normal">{item.unit}</span>
                      </span>
                      <span className="text-xs text-muted-foreground tabular">
                        {previous
                          ? `${signed(latest.value - previous.value)} с прошлого раза`
                          : 'один замер'}
                      </span>
                      {item.entries.length > 2 && (
                        <span className="text-xs text-muted-foreground tabular">
                          {signed(latest.value - first.value)} с{' '}
                          {formatDay(first.measured_on, 'd MMM')}
                        </span>
                      )}
                      {points.length > 1 && (
                        <span className="pointer-events-none block" aria-hidden="true">
                          <TrendLine
                            points={points}
                            unit={item.unit}
                            name={item.label}
                            height={48}
                            compact
                          />
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
            {active && (
              <section aria-label={`${active.label}: все замеры`}>
                <h3 className="section-title mb-1">{active.label}</h3>
                <ul className="row-list -mx-2">
                  {active.entries.map((entry) => (
                    <li key={entry.id} className="flex items-center gap-3 px-2 py-1.5">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium tabular">
                          {num(entry.value, 1)} {active.unit}
                        </p>
                        <p className="truncate text-sm text-muted-foreground">
                          {dateTimeLabel(entry.measured_at, today)}
                          {SOURCE[entry.source] ? ` · ${SOURCE[entry.source]}` : ''}
                          {entry.note ? ` · ${entry.note}` : ''}
                        </p>
                      </div>
                      <RowMenu
                        label={`${active.label} ${num(entry.value, 1)}`}
                        onEdit={() => setEditing(entry)}
                        onDelete={() => setDeleting(entry)}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </CardContent>
      <ResponsiveSheet open={writing} onOpenChange={setWriting} title="Замеры" wide>
        {writing && <MeasurementsForm latest={list} onDone={() => setWriting(false)} />}
      </ResponsiveSheet>
      <MeasurementSheet
        open={editing !== undefined}
        onOpenChange={(value) => !value && setEditing(undefined)}
        entry={editing ?? null}
        defaultKind={active?.value ?? 'waist'}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(value) => !value && setDeleting(null)}
        title="Удалить замер?"
        description={
          deleting
            ? `${measurement(deleting.kind).label}: ${num(deleting.value, 1)} ${measurement(deleting.kind).unit}, ${dateTimeLabel(deleting.measured_at)}`
            : undefined
        }
        onConfirm={() => remove.mutateAsync(deleting!.id)}
      />
    </Card>
  )
}

/** All measurements of one sitting at once; the last values are shown as hints. */
function MeasurementsForm({ latest, onDone }: { latest: Measurement[]; onDone: () => void }) {
  const user = useUser()
  const client = useQueryClient()
  const [values, setValues] = useState<Partial<Record<MeasurementKind, string>>>({})
  const [when, setWhen] = useState(nowIn(user.timezone))
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const last = (kind: MeasurementKind) => latest.find((entry) => entry.kind === kind)
  const save = useMutation({
    mutationFn: () => {
      const numbers: Partial<Record<MeasurementKind, number>> = {}
      for (const item of MEASUREMENTS) {
        const text = values[item.value]?.trim()
        if (!text) continue
        const number = parseNumber(text)
        const limit = item.value === 'body_fat' ? 75 : 300
        if (number === null || number <= 0 || number > limit)
          throw new Error(`${item.label}: от 0 до ${limit} ${item.unit}`)
        numbers[item.value] = number
      }
      if (!Object.keys(numbers).length) throw new Error('Впишите хотя бы один замер')
      return bodyApi.addMeasurements({
        values: numbers,
        measured_at: when || null,
        note: note.trim() || null,
      })
    },
    onMutate: () => setError(''),
    onSuccess: async (saved) => {
      await invalidateBody(client)
      toast.success(saved.length > 1 ? `Записано замеров: ${saved.length}` : 'Замер записан')
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
        save.mutate()
      }}
    >
      <p className="text-sm text-muted-foreground">
        Заполните то, что измерили, остальное оставьте пустым.
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-4">
        {MEASUREMENTS.map((item) => {
          const previous = last(item.value)
          return (
            <label key={item.value} className="flex min-w-0 flex-col gap-1.5">
              <span className="text-sm font-medium">{item.label}</span>
              <span className="relative">
                <Input
                  value={values[item.value] ?? ''}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [item.value]: event.target.value }))
                  }
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder={previous ? inputNumber(previous.value) : ''}
                  aria-label={`${item.label}, ${item.unit}`}
                  className="pr-9 text-lg tabular"
                />
                <span
                  className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted-foreground"
                  aria-hidden="true"
                >
                  {item.unit}
                </span>
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {previous ? `было ${formatDay(previous.measured_on, 'd MMM')}` : 'еще не мерили'}
              </span>
            </label>
          )
        })}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor="measurements-time">Когда</Label>
          <Input
            id="measurements-time"
            type="datetime-local"
            value={when}
            max={`${todayIn(user.timezone)}T23:59`}
            onChange={(event) => setWhen(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="measurements-note">Заметка</Label>
          <Input
            id="measurements-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={300}
            placeholder="Например, утром до еды"
          />
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Сохраняем…' : 'Сохранить замеры'}
      </Button>
    </form>
  )
}

function MeasurementSheet({
  open,
  onOpenChange,
  entry,
  defaultKind,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  entry: Measurement | null
  defaultKind: MeasurementKind
}) {
  return (
    <ResponsiveSheet
      open={open}
      onOpenChange={onOpenChange}
      title={entry ? 'Замер' : 'Новый замер'}
    >
      {open && (
        <MeasurementForm
          entry={entry}
          defaultKind={defaultKind}
          onDone={() => onOpenChange(false)}
        />
      )}
    </ResponsiveSheet>
  )
}

function MeasurementForm({
  entry,
  defaultKind,
  onDone,
}: {
  entry: Measurement | null
  defaultKind: MeasurementKind
  onDone: () => void
}) {
  const user = useUser()
  const client = useQueryClient()
  const [kind, setKind] = useState<MeasurementKind>(entry?.kind ?? defaultKind)
  const [value, setValue] = useState(inputNumber(entry?.value))
  const [when, setWhen] = useState(entry ? localInput(entry.measured_at) : nowIn(user.timezone))
  const [note, setNote] = useState(entry?.note ?? '')
  const [error, setError] = useState('')
  const unit = measurement(kind).unit
  const save = useMutation({
    mutationFn: () => {
      const number = parseNumber(value)
      const limit = kind === 'body_fat' ? 75 : 300
      if (number === null || number <= 0 || number > limit)
        throw new Error(`Значение от 0 до ${limit} ${unit}`)
      const data = { kind, value: number, measured_at: when || null, note: note.trim() || null }
      return entry ? bodyApi.updateMeasurement(entry.id, data) : bodyApi.addMeasurement(data)
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await invalidateBody(client)
      toast.success('Замер сохранен')
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
        save.mutate()
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="measurement-kind">Что измеряем</Label>
        <Select value={kind} onValueChange={(next) => setKind(next as MeasurementKind)}>
          <SelectTrigger id="measurement-kind">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MEASUREMENTS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}, {item.unit}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="measurement-value">Значение, {unit}</Label>
        <Input
          id="measurement-value"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          inputMode="decimal"
          autoComplete="off"
          required
          className="text-lg"
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="measurement-time">Когда</Label>
        <Input
          id="measurement-time"
          type="datetime-local"
          value={when}
          max={`${todayIn(user.timezone)}T23:59`}
          onChange={(event) => setWhen(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="measurement-note">Заметка</Label>
        <Input
          id="measurement-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Сохраняем…' : 'Сохранить'}
      </Button>
    </form>
  )
}
