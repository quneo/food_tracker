import { api, json, query } from './client'
import type {
  AdminUser,
  AiStatus,
  AuthConfig,
  ChatMessage,
  DailyRow,
  DaySummary,
  Fact,
  FactCategory,
  Invite,
  LoginPoll,
  LoginRequest,
  Meal,
  MealIn,
  MealPatch,
  MealType,
  MealStatus,
  Measurement,
  MeasurementIn,
  Pose,
  Profile,
  ProgressPhoto,
  Reminder,
  ReminderIn,
  Report,
  SuggestedTargets,
  AiUsage,
  TelegramWidgetUser,
  User,
  TelegramLink,
  Weight,
  WeightIn,
  Product,
  ProductIn,
} from '@/types'

type Signal = { signal?: AbortSignal }

export const authApi = {
  me: ({ signal }: Signal = {}) => api<User>('/auth/me', { signal }),
  config: ({ signal }: Signal = {}) => api<AuthConfig>('/auth/config', { signal }),
  widget: (user: TelegramWidgetUser, invite?: string | null) =>
    api<User>('/auth/telegram', json('POST', { ...user, invite: invite || undefined })),
  webapp: (initData: string, invite?: string | null) =>
    api<User>('/auth/webapp', json('POST', { init_data: initData, invite: invite || undefined })),
  bastion: (username: string, password: string, totpCode: string) =>
    api<User>('/auth/bastion', json('POST', { username, password, totp_code: totpCode || null })),
  telegramLink: () => api<TelegramLink>('/auth/telegram-link', { method: 'POST' }),
  startBotLogin: () => api<LoginRequest>('/auth/login-requests', { method: 'POST' }),
  pollBotLogin: (code: string, pollToken: string, signal?: AbortSignal) =>
    api<LoginPoll>('/auth/login-requests/poll', {
      ...json('POST', { code, poll_token: pollToken }),
      signal,
    }),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
  logoutAll: () => api<void>('/auth/logout-all', { method: 'POST' }),
  deleteAccount: (confirm: string) => api<void>('/auth/account', json('DELETE', { confirm })),
}

export const mealsApi = {
  today: ({ signal }: Signal = {}) => api<DaySummary>('/today', { signal }),
  list: (
    params: { from: string; to: string; meal_type?: MealType | null; status?: MealStatus | null },
    { signal }: Signal = {},
  ) => api<Meal[]>(`/meals${query(params)}`, { signal }),
  get: (id: number, { signal }: Signal = {}) => api<Meal>(`/meals/${id}`, { signal }),
  create: (data: MealIn) => api<Meal>('/meals', json('POST', data)),
  update: (id: number, data: MealPatch) => api<Meal>(`/meals/${id}`, json('PATCH', data)),
  confirm: (id: number) => api<Meal>(`/meals/${id}/confirm`, { method: 'POST' }),
  remove: (id: number) => api<void>(`/meals/${id}`, { method: 'DELETE' }),
  addPhoto: (id: number, file: File) => {
    const form = new FormData()
    form.append('photo', file)
    return api<Meal>(`/meals/${id}/photos`, { method: 'POST', body: form })
  },
  removePhoto: (id: number, mediaId: number) =>
    api<Meal>(`/meals/${id}/photos/${mediaId}`, { method: 'DELETE' }),
}

export const productsApi = {
  list: (q: string | null, { signal }: Signal = {}) =>
    api<Product[]>(`/products${query({ q })}`, { signal }),
  create: (data: ProductIn) => api<Product>('/products', json('POST', data)),
  update: (id: number, data: Partial<ProductIn>) =>
    api<Product>(`/products/${id}`, json('PATCH', data)),
  remove: (id: number) => api<void>(`/products/${id}`, { method: 'DELETE' }),
  addPhoto: (id: number, file: File) => {
    const form = new FormData()
    form.append('photo', file)
    return api<Product>(`/products/${id}/photos`, { method: 'POST', body: form })
  },
  removePhoto: (id: number, mediaId: number) =>
    api<Product>(`/products/${id}/photos/${mediaId}`, { method: 'DELETE' }),
}

export const analyticsApi = {
  daily: (from: string, to: string, { signal }: Signal = {}) =>
    api<DailyRow[]>(`/analytics/daily${query({ from, to })}`, { signal }),
  report: (from: string, to: string, includePartial: boolean, { signal }: Signal = {}) =>
    api<Report>(
      `/analytics/report${query({ from, to, include_partial: includePartial || undefined })}`,
      { signal },
    ),
  markDay: (day: string, complete: boolean | null) =>
    api<void>(`/analytics/days/${day}`, json('PUT', { complete })),
}

// Weights and measurements take `start`/`end`, unlike meals and analytics (`from`/`to`).
export const bodyApi = {
  weights: (range: { start?: string; end?: string } = {}, { signal }: Signal = {}) =>
    api<Weight[]>(`/weights${query(range)}`, { signal }),
  addWeight: (data: WeightIn) => api<Weight>('/weights', json('POST', data)),
  updateWeight: (id: number, data: WeightIn) => api<Weight>(`/weights/${id}`, json('PUT', data)),
  removeWeight: (id: number) => api<void>(`/weights/${id}`, { method: 'DELETE' }),
  measurements: (range: { start?: string; end?: string } = {}, { signal }: Signal = {}) =>
    api<Measurement[]>(`/measurements${query(range)}`, { signal }),
  addMeasurement: (data: MeasurementIn) => api<Measurement>('/measurements', json('POST', data)),
  updateMeasurement: (id: number, data: MeasurementIn) =>
    api<Measurement>(`/measurements/${id}`, json('PUT', data)),
  removeMeasurement: (id: number) => api<void>(`/measurements/${id}`, { method: 'DELETE' }),
  photos: ({ signal }: Signal = {}) => api<ProgressPhoto[]>('/progress-photos', { signal }),
  uploadPhoto: (data: { file: File; taken_on?: string; pose: Pose; note?: string }) => {
    const form = new FormData()
    form.append('photo', data.file)
    if (data.taken_on) form.append('taken_on', data.taken_on)
    form.append('pose', data.pose)
    if (data.note) form.append('note', data.note)
    return api<ProgressPhoto>('/progress-photos', { method: 'POST', body: form })
  },
  updatePhoto: (id: number, data: { taken_on?: string; pose?: Pose; note?: string | null }) =>
    api<ProgressPhoto>(`/progress-photos/${id}`, json('PATCH', data)),
  removePhoto: (id: number) => api<void>(`/progress-photos/${id}`, { method: 'DELETE' }),
}

export const profileApi = {
  get: ({ signal }: Signal = {}) => api<Profile>('/profile', { signal }),
  save: (data: Profile) => api<Profile>('/profile', json('PUT', data)),
  suggested: () => api<SuggestedTargets>('/profile/suggested-targets'),
  aiUsage: ({ signal }: Signal = {}) => api<AiUsage>('/profile/ai-usage', { signal }),
}

export const remindersApi = {
  list: ({ signal }: Signal = {}) => api<Reminder[]>('/reminders', { signal }),
  create: (data: ReminderIn) => api<Reminder>('/reminders', json('POST', data)),
  update: (id: number, data: ReminderIn) => api<Reminder>(`/reminders/${id}`, json('PUT', data)),
  remove: (id: number) => api<void>(`/reminders/${id}`, { method: 'DELETE' }),
}

export const memoryApi = {
  list: ({ signal }: Signal = {}) => api<Fact[]>('/memory', { signal }),
  create: (data: { category: FactCategory; text: string }) =>
    api<Fact>('/memory', json('POST', data)),
  update: (id: number, data: { category: FactCategory; text: string }) =>
    api<Fact>(`/memory/${id}`, json('PUT', data)),
  remove: (id: number) => api<void>(`/memory/${id}`, { method: 'DELETE' }),
  messages: (before?: number, limit = 50, { signal }: Signal = {}) =>
    api<ChatMessage[]>(`/chat/messages${query({ before, limit })}`, { signal }),
  clearMessages: () => api<void>('/chat/messages', { method: 'DELETE' }),
}

export const adminApi = {
  users: ({ signal }: Signal = {}) => api<AdminUser[]>('/admin/users', { signal }),
  setBlocked: (id: number, isBlocked: boolean) =>
    api<{ id: number; is_blocked: boolean }>(
      `/admin/users/${id}`,
      json('PATCH', { is_blocked: isBlocked }),
    ),
  removeUser: (id: number) => api<void>(`/admin/users/${id}`, { method: 'DELETE' }),
  invites: ({ signal }: Signal = {}) => api<Invite[]>('/admin/invites', { signal }),
  createInvite: (data: { note: string | null; max_uses: number; days: number | null }) =>
    api<Invite>('/admin/invites', json('POST', data)),
  revokeInvite: (id: number) => api<void>(`/admin/invites/${id}`, { method: 'DELETE' }),
  ai: ({ signal }: Signal = {}) => api<AiStatus>('/admin/ai', { signal }),
}
