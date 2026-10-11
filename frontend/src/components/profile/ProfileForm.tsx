import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Calculator } from 'lucide-react'
import { toast } from 'sonner'
import { profileApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ACTIVITIES, GOALS, SEXES } from '@/lib/labels'
import { inputNumber, num, parseNumber } from '@/lib/format'
import { TimezonePicker } from './TimezonePicker'
import type { Activity, Goal, Profile, Sex, SuggestedTargets } from '@/types'

interface Form {
  sex: Sex | null
  birth_date: string
  height_cm: string
  activity: Activity | null
  goal: Goal | null
  target_weight_kg: string
  kcal_target: string
  protein_target: string
  fat_target: string
  carbs_target: string
  timezone: string
  about: string
  auto_confirm_meals: boolean
}

const toForm = (profile: Profile): Form => ({
  sex: profile.sex,
  birth_date: profile.birth_date ?? '',
  height_cm: inputNumber(profile.height_cm),
  activity: profile.activity,
  goal: profile.goal,
  target_weight_kg: inputNumber(profile.target_weight_kg),
  kcal_target: inputNumber(profile.kcal_target),
  protein_target: inputNumber(profile.protein_target),
  fat_target: inputNumber(profile.fat_target),
  carbs_target: inputNumber(profile.carbs_target),
  timezone: profile.timezone,
  about: profile.about ?? '',
  auto_confirm_meals: profile.auto_confirm_meals,
})

const NUMBERS: { field: keyof Form; name: string; min: number; max: number; integer?: boolean }[] =
  [
    { field: 'height_cm', name: 'Рост', min: 100, max: 250 },
    { field: 'target_weight_kg', name: 'Целевой вес', min: 30, max: 300 },
    { field: 'kcal_target', name: 'Калории', min: 800, max: 6000, integer: true },
    { field: 'protein_target', name: 'Белки', min: 0, max: 500, integer: true },
    { field: 'fat_target', name: 'Жиры', min: 0, max: 400, integer: true },
    { field: 'carbs_target', name: 'Углеводы', min: 0, max: 1000, integer: true },
  ]

function toProfile(form: Form): Profile | string {
  const values: Record<string, number | null> = {}
  for (const { field, name, min, max, integer } of NUMBERS) {
    const text = String(form[field])
    const value = parseNumber(text)
    if (text.trim() && value === null) return `${name}: введите число`
    if (value !== null && (value < min || value > max))
      return `${name}: от ${num(min)} до ${num(max)}`
    values[field] = value === null ? null : integer ? Math.round(value) : value
  }
  return {
    sex: form.sex,
    birth_date: form.birth_date || null,
    height_cm: values.height_cm,
    activity: form.activity,
    goal: form.goal,
    target_weight_kg: values.target_weight_kg,
    kcal_target: values.kcal_target,
    protein_target: values.protein_target,
    fat_target: values.fat_target,
    carbs_target: values.carbs_target,
    timezone: form.timezone,
    about: form.about.trim() || null,
    auto_confirm_meals: form.auto_confirm_meals,
  }
}

function Choice<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T | null
  onChange: (value: T | null) => void
}) {
  const id = `choice-${label}`
  return (
    <div className="flex flex-col gap-2">
      <span id={id} className="text-sm font-medium">
        {label}
      </span>
      <div className="chips" role="radiogroup" aria-labelledby={id}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            data-state={value === option.value ? 'on' : 'off'}
            className="chip"
            onClick={() => onChange(value === option.value ? null : option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function NumberField({
  id,
  label,
  value,
  onChange,
  suffix,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  suffix?: string
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          inputMode="decimal"
          autoComplete="off"
          className={suffix ? 'pr-12' : undefined}
        />
        {suffix && (
          <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted-foreground">
            {suffix}
          </span>
        )}
      </div>
    </div>
  )
}

export function ProfileForm({ profile }: { profile: Profile }) {
  const client = useQueryClient()
  const { refresh } = useAuth()
  const initial = toForm(profile)
  const [form, setForm] = useState<Form>(initial)
  const [error, setError] = useState('')
  const [suggestion, setSuggestion] = useState<SuggestedTargets | null>(null)
  const dirty = JSON.stringify(form) !== JSON.stringify(initial)

  const set = <K extends keyof Form>(field: K, value: Form[K]) =>
    setForm((current) => ({ ...current, [field]: value }))

  async function persist() {
    const data = toProfile(form)
    if (typeof data === 'string') throw new Error(data)
    const saved = await profileApi.save(data)
    client.setQueryData(keys.profile, saved)
    if (saved.timezone !== profile.timezone) {
      // Days and times are counted in the new zone from now on.
      await refresh().catch(() => undefined)
      await client.invalidateQueries()
    } else {
      await Promise.all(
        [keys.today, keys.daily, keys.report, keys.reminders].map((queryKey) =>
          client.invalidateQueries({ queryKey }),
        ),
      )
    }
    return saved
  }

  const save = useMutation({
    mutationFn: persist,
    onMutate: () => setError(''),
    onSuccess: (saved) => {
      setForm(toForm(saved))
      toast.success('Профиль сохранен')
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })

  const suggest = useMutation({
    mutationFn: async () => {
      // The calculation uses saved data: save edits first.
      if (dirty) await persist()
      return profileApi.suggested()
    },
    onMutate: () => setError(''),
    onSuccess: (value) => {
      setSuggestion(value)
      setForm((current) => ({
        ...current,
        kcal_target: String(value.kcal),
        protein_target: String(value.protein),
        fat_target: String(value.fat),
        carbs_target: String(value.carbs),
      }))
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
      <Card>
        <CardHeader>
          <CardTitle>О себе</CardTitle>
          <CardDescription>Нужно для расчета нормы калорий.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <Choice
            label="Пол"
            options={SEXES}
            value={form.sex}
            onChange={(value) => set('sex', value)}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="birth-date">Дата рождения</Label>
              <Input
                id="birth-date"
                type="date"
                value={form.birth_date}
                min="1900-01-02"
                onChange={(event) => set('birth_date', event.target.value)}
              />
            </div>
            <NumberField
              id="height"
              label="Рост"
              suffix="см"
              value={form.height_cm}
              onChange={(value) => set('height_cm', value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="activity">Активность</Label>
            <Select
              value={form.activity ?? ''}
              onValueChange={(value) => set('activity', value as Activity)}
            >
              <SelectTrigger id="activity">
                <SelectValue placeholder="Не указана" />
              </SelectTrigger>
              <SelectContent>
                {ACTIVITIES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    <span className="flex flex-col items-start">
                      <span>{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.hint}</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Choice
            label="Цель"
            options={GOALS}
            value={form.goal}
            onChange={(value) => set('goal', value)}
          />
          <div className="sm:max-w-[calc(50%-8px)]">
            <NumberField
              id="target-weight"
              label="Целевой вес"
              suffix="кг"
              value={form.target_weight_kg}
              onChange={(value) => set('target_weight_kg', value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Цели на день</CardTitle>
          <CardDescription>
            «Рассчитать» предложит норму по формуле Миффлина — Сан Жеора; ее можно поправить.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <NumberField
              id="kcal"
              label="Калории"
              suffix="ккал"
              value={form.kcal_target}
              onChange={(value) => set('kcal_target', value)}
            />
            <NumberField
              id="protein"
              label="Белки"
              suffix="г"
              value={form.protein_target}
              onChange={(value) => set('protein_target', value)}
            />
            <NumberField
              id="fat"
              label="Жиры"
              suffix="г"
              value={form.fat_target}
              onChange={(value) => set('fat_target', value)}
            />
            <NumberField
              id="carbs"
              label="Углеводы"
              suffix="г"
              value={form.carbs_target}
              onChange={(value) => set('carbs_target', value)}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            className="self-start"
            onClick={() => suggest.mutate()}
            disabled={suggest.isPending}
          >
            <Calculator />
            {suggest.isPending ? 'Считаем…' : 'Рассчитать'}
          </Button>
          {suggestion && (
            <div className="rounded-[14px] bg-accent px-4 py-3 text-sm" role="status">
              <p>
                Базовый обмен — <b>{num(suggestion.bmr)} ккал</b>, с учетом активности —{' '}
                <b>{num(suggestion.tdee)} ккал</b>. Норма с учетом цели —{' '}
                <b>{num(suggestion.kcal)} ккал</b>.
              </p>
              <p className="mt-1 text-muted-foreground">
                Цифры подставлены в поля выше. Сохраните, если подходят; через 2–3 недели сверьтесь
                с динамикой веса.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ассистент и время</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="timezone">Часовой пояс</Label>
            <TimezonePicker
              id="timezone"
              value={form.timezone}
              onChange={(value) => set('timezone', value)}
            />
            <p className="text-xs text-muted-foreground">
              По нему считаются дни, время записей и напоминания.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="about">Что важно знать ассистенту</Label>
            <Textarea
              id="about"
              value={form.about}
              onChange={(event) => set('about', event.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="Режим дня, ограничения, как обычно питаетесь"
            />
          </div>
          <div className="flex items-start justify-between gap-4">
            <Label htmlFor="auto-confirm" className="flex flex-col items-start gap-1 font-normal">
              <span className="font-medium">Сохранять записи от бота сразу</span>
              <span className="text-sm text-muted-foreground">
                Без черновика и кнопки подтверждения
              </span>
            </Label>
            <Switch
              id="auto-confirm"
              checked={form.auto_confirm_meals}
              onCheckedChange={(value) => set('auto_confirm_meals', value)}
              className="mt-1"
            />
          </div>
        </CardContent>
      </Card>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {(dirty || save.isPending) && (
        <div className="sticky bottom-[calc(var(--nav-height)+env(safe-area-inset-bottom)+8px)] z-10 flex items-center justify-between gap-3 rounded-[16px] border bg-popover/95 p-2 pl-4 shadow-lg backdrop-blur min-[900px]:bottom-4">
          <span className="text-sm text-muted-foreground">Есть несохраненные изменения</span>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? 'Сохраняем…' : 'Сохранить'}
          </Button>
        </div>
      )}
    </form>
  )
}
