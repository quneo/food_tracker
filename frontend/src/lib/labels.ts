import type {
  Activity,
  Confidence,
  FactCategory,
  Goal,
  MealType,
  MeasurementKind,
  Pose,
  ReminderKind,
  Sex,
} from '@/types'

export const MEAL_TYPES: { value: MealType; label: string }[] = [
  { value: 'breakfast', label: 'Завтрак' },
  { value: 'lunch', label: 'Обед' },
  { value: 'dinner', label: 'Ужин' },
  { value: 'snack', label: 'Перекус' },
]
export const mealTypeLabel = (value: MealType | null) =>
  MEAL_TYPES.find((item) => item.value === value)?.label ?? 'Прием пищи'

export const CONFIDENCE: Record<Confidence, string> = {
  low: 'низкая',
  medium: 'средняя',
  high: 'высокая',
}

export const MACROS = [
  { key: 'protein', label: 'Белки', short: 'Б' },
  { key: 'fat', label: 'Жиры', short: 'Ж' },
  { key: 'carbs', label: 'Углеводы', short: 'У' },
] as const
export type MacroKey = (typeof MACROS)[number]['key']

export const POSES: { value: Pose; label: string }[] = [
  { value: 'front', label: 'Спереди' },
  { value: 'side', label: 'Сбоку' },
  { value: 'back', label: 'Сзади' },
  { value: 'other', label: 'Другое' },
]
export const poseLabel = (value: Pose) => POSES.find((item) => item.value === value)?.label ?? ''

export const MEASUREMENTS: { value: MeasurementKind; label: string; unit: string }[] = [
  { value: 'waist', label: 'Талия', unit: 'см' },
  { value: 'hips', label: 'Бедра', unit: 'см' },
  { value: 'chest', label: 'Грудь', unit: 'см' },
  { value: 'neck', label: 'Шея', unit: 'см' },
  { value: 'arm', label: 'Бицепс', unit: 'см' },
  { value: 'thigh', label: 'Бедро', unit: 'см' },
  { value: 'calf', label: 'Голень', unit: 'см' },
  { value: 'body_fat', label: 'Процент жира', unit: '%' },
]
export const measurement = (kind: MeasurementKind) =>
  MEASUREMENTS.find((item) => item.value === kind) ?? { value: kind, label: kind, unit: 'см' }

export const SEXES: { value: Sex; label: string }[] = [
  { value: 'female', label: 'Женский' },
  { value: 'male', label: 'Мужской' },
]

export const ACTIVITIES: { value: Activity; label: string; hint: string }[] = [
  { value: 'sedentary', label: 'Минимальная', hint: 'Сидячая работа, без тренировок' },
  { value: 'light', label: 'Низкая', hint: 'Прогулки, 1–3 легкие тренировки в неделю' },
  { value: 'moderate', label: 'Средняя', hint: '3–5 тренировок в неделю' },
  { value: 'high', label: 'Высокая', hint: '6–7 тренировок в неделю' },
  { value: 'very_high', label: 'Очень высокая', hint: 'Физическая работа или спорт дважды в день' },
]

export const GOALS: { value: Goal; label: string }[] = [
  { value: 'lose', label: 'Снизить вес' },
  { value: 'maintain', label: 'Держать вес' },
  { value: 'gain', label: 'Набрать вес' },
]

export const FACT_CATEGORIES: { value: FactCategory; label: string }[] = [
  { value: 'goal', label: 'Цели' },
  { value: 'preference', label: 'Предпочтения' },
  { value: 'dislike', label: 'Не ест или не любит' },
  { value: 'allergy', label: 'Аллергии' },
  { value: 'health', label: 'Здоровье' },
  { value: 'habit', label: 'Привычки' },
  { value: 'food', label: 'Блюда и продукты' },
  { value: 'other', label: 'Другое' },
]

export const REMINDER_KINDS: { value: ReminderKind; label: string }[] = [
  { value: 'meal', label: 'Записать питание' },
  { value: 'weight', label: 'Взвеситься' },
  { value: 'photo', label: 'Фото прогресса' },
  { value: 'review', label: 'Разбор рациона' },
  { value: 'custom', label: 'Свое напоминание' },
]
export const reminderLabel = (kind: ReminderKind) =>
  REMINDER_KINDS.find((item) => item.value === kind)?.label ?? ''

export const WEEKDAYS = [
  { value: 1, short: 'Пн', label: 'понедельник' },
  { value: 2, short: 'Вт', label: 'вторник' },
  { value: 3, short: 'Ср', label: 'среда' },
  { value: 4, short: 'Чт', label: 'четверг' },
  { value: 5, short: 'Пт', label: 'пятница' },
  { value: 6, short: 'Сб', label: 'суббота' },
  { value: 7, short: 'Вс', label: 'воскресенье' },
]
