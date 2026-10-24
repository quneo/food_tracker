// Shapes of the backend API (backend/app/api, backend/app/*/schemas.py).
// Times like "2026-10-11T13:20+07:00" are local to the person's own time zone;
// days like "2026-10-11" are local dates.

export interface User {
  id: number
  name: string
  first_name: string | null
  /** Telegram username. */
  username: string | null
  /** Empty until a person who signed in with Bastion links Telegram. */
  telegram_id: number | null
  /** Bastion login. */
  login: string | null
  bastion: boolean
  is_admin: boolean
  timezone: string
  created_at: string
}

export interface AuthConfig {
  bot_username: string
  registration: 'bastion' | 'invite' | 'open'
  widget: boolean
  bastion: boolean
  bastion_url: string | null
}

export interface TelegramLink {
  /** One-time key; the person sends "/link <key>" to the bot. */
  code: string
  command: string
  bot_username: string
  expires_in: number
}

export interface LoginRequest {
  code: string
  poll_token: string
  link: string
  expires_in: number
}

export type LoginStatus = 'pending' | 'confirmed' | 'rejected' | 'expired'

export interface LoginPoll {
  status: LoginStatus
  user?: User
}

export interface TelegramWidgetUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

// Meals

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'
export type Confidence = 'low' | 'medium' | 'high'
export type GramsSource = 'estimated' | 'stated' | 'label'
export type MealStatus = 'draft' | 'confirmed'

export interface MealItem {
  id: number
  name: string
  /** A saved product the numbers came from. */
  product_id: number | null
  grams: number | null
  grams_source: GramsSource
  kcal: number
  protein: number
  fat: number
  carbs: number
  confidence: Confidence | null
  note: string | null
}

export interface MealItemIn {
  name: string
  product_id?: number | null
  grams: number | null
  grams_source: GramsSource
  kcal: number
  protein: number
  fat: number
  carbs: number
  confidence?: Confidence | null
  note?: string | null
}

export interface MealPhoto {
  id: number
  width: number
  height: number
}

export interface Meal {
  id: number
  status: MealStatus
  meal_type: MealType | null
  title: string
  eaten_at: string
  eaten_on: string
  note: string | null
  source: string
  kcal: number
  protein: number
  fat: number
  carbs: number
  estimated_by: string
  confidence: Confidence | null
  kcal_low: number | null
  kcal_high: number | null
  assumptions: string[]
  /** The assistant's remark about the meal. */
  ai_comment: string | null
  items: MealItem[]
  photos: MealPhoto[]
  created_at: string
}

export interface MealIn {
  title: string
  meal_type: MealType | null
  eaten_at?: string | null
  note?: string | null
  items: MealItemIn[]
}

export type MealPatch = Partial<MealIn>

export interface Totals {
  kcal: number
  protein: number
  fat: number
  carbs: number
}

export interface Targets {
  kcal: number | null
  protein: number | null
  fat: number | null
  carbs: number | null
}

export interface DaySummary {
  day: string
  totals: Totals
  targets: Targets
  meals: Meal[]
  drafts: number
}

/** What the photos sent to the assistant show. */
export type RecordMode = 'food' | 'label'

export interface AssistantJob {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  reply: string | null
  notes: string[]
  meals: Meal[]
  error: string | null
}

// Analytics

export type DayStatus = 'empty' | 'partial' | 'complete'

export interface DailyRow {
  day: string
  meals: number
  kcal: number
  protein: number
  fat: number
  carbs: number
  weight: number | null
  status: DayStatus
  marked: boolean
}

export interface Report {
  start: string
  end: string
  days: number
  logged_days: number
  complete_days: number
  counted_days: number
  include_partial: boolean
  averages: Record<'kcal' | 'protein' | 'fat' | 'carbs', number | null>
  targets: Targets
  days_within_target: number | null
  macro_split: { protein: number; fat: number; carbs: number } | null
  weight: {
    first: number
    last: number
    change: number
    min: number
    max: number
    entries: number
  } | null
  measurements: {
    kind: MeasurementKind
    name: string
    unit: string
    first: number
    last: number
    change: number
  }[]
  top_foods: { name: string; count: number }[]
}

// Body

export interface Weight {
  id: number
  weight_kg: number
  measured_at: string
  measured_on: string
  note: string | null
  source: string
}

export interface WeightIn {
  weight_kg: number
  measured_at?: string | null
  note?: string | null
}

export type MeasurementKind =
  'waist' | 'hips' | 'chest' | 'neck' | 'arm' | 'thigh' | 'calf' | 'body_fat'

export interface Measurement {
  id: number
  kind: MeasurementKind
  value: number
  unit: string
  measured_at: string
  measured_on: string
  note: string | null
  source: string
}

export interface MeasurementIn {
  kind: MeasurementKind
  value: number
  measured_at?: string | null
  note?: string | null
}

export type Pose = 'front' | 'side' | 'back' | 'other'

export interface ProgressPhoto {
  id: number
  entry_id: number
  media_id: number
  taken_on: string
  pose: Pose
  note: string | null
  width: number
  height: number
  weight_kg: number | null
}

/** One day's set of progress photos: front, back, side together. */
export interface ProgressEntry {
  id: number
  taken_on: string
  note: string | null
  weight_kg: number | null
  photos: { id: number; media_id: number; pose: Pose; width: number; height: number }[]
}

export interface PhotoLock {
  enabled: boolean
  unlocked: boolean
  unlocked_until: string | null
  blocked_until: string | null
}

// Profile

export type Sex = 'male' | 'female'
export type Activity = 'sedentary' | 'light' | 'moderate' | 'high' | 'very_high'
export type Goal = 'lose' | 'maintain' | 'gain'

export interface Profile {
  sex: Sex | null
  birth_date: string | null
  height_cm: number | null
  activity: Activity | null
  goal: Goal | null
  target_weight_kg: number | null
  kcal_target: number | null
  protein_target: number | null
  fat_target: number | null
  carbs_target: number | null
  timezone: string
  about: string | null
  auto_confirm_meals: boolean
}

/** Codex's token counts; cached input is part of input, reasoning part of output. */
export interface AiUsagePeriod {
  key: 'today' | 'week' | 'month' | 'all'
  label: string
  requests: number
  /** Requests that came with token counts (older ones may not). */
  measured: number
  input: number
  cached: number
  output: number
  reasoning: number
  total: number
  /** USD, when prices are set on the server. */
  cost: number | null
}

export interface AiUsage {
  periods: AiUsagePeriod[]
  model: string | null
  priced: boolean
}

export interface SuggestedTargets {
  kcal: number
  protein: number
  fat: number
  carbs: number
  bmr: number
  tdee: number
}

export type ReminderKind = 'meal' | 'weight' | 'photo' | 'measure' | 'review' | 'custom'

/** A saved product with numbers from its label, per 100 g (or 100 ml). */
export interface Product {
  id: number
  name: string
  brand: string | null
  kcal: number
  protein: number
  fat: number
  carbs: number
  portion_name: string | null
  portion_grams: number | null
  package_grams: number | null
  comment: string | null
  uses: number
  last_used_at: string | null
  created_at: string
  photos: MealPhoto[]
}

export type ProductIn = Omit<Product, 'id' | 'uses' | 'last_used_at' | 'created_at' | 'photos'>

export interface Reminder {
  id: number
  kind: ReminderKind
  time: string
  days: number[]
  every_weeks: number
  text: string | null
  enabled: boolean
  smart_skip: boolean
  description: string
  next_run_at: string | null
}

export interface ReminderIn {
  kind: ReminderKind
  time: string
  days: number[]
  every_weeks: number
  text: string | null
  enabled: boolean
  smart_skip: boolean
}

export type FactCategory =
  'goal' | 'preference' | 'dislike' | 'allergy' | 'health' | 'habit' | 'food' | 'other'

export interface Fact {
  id: number
  category: FactCategory
  text: string
  source: 'ai' | 'user'
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  photos: number
  created_at: string
}

// Administration

export interface Invite {
  id: number
  note: string | null
  link: string
  max_uses: number
  uses: number
  created_at: string
  expires_at: string | null
  revoked: boolean
  usable: boolean
}

export interface AdminUser {
  id: number
  name: string
  username: string | null
  /** Bastion login. */
  login: string | null
  telegram: boolean
  bastion_active: boolean
  is_admin: boolean
  is_blocked: boolean
  created_at: string
  last_seen_at: string | null
  meals: number
}

export interface AiStatus {
  runner: 'ssh' | 'local' | 'off'
  queued: number
  done: number
  failed: number
  average_ms: number | null
  last_error: string | null
}
