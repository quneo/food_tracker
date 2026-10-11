import type { QueryClient } from '@tanstack/react-query'

export const keys = {
  authConfig: ['auth-config'] as const,
  today: ['today'] as const,
  meals: ['meals'] as const,
  meal: (id: number) => ['meal', id] as const,
  daily: ['daily'] as const,
  report: ['report'] as const,
  weights: ['weights'] as const,
  measurements: ['measurements'] as const,
  photos: ['progress-photos'] as const,
  profile: ['profile'] as const,
  suggested: ['suggested-targets'] as const,
  reminders: ['reminders'] as const,
  memory: ['memory'] as const,
  chat: ['chat'] as const,
  admin: ['admin'] as const,
}

function invalidate(client: QueryClient, list: readonly (readonly unknown[])[]) {
  return Promise.all(list.map((queryKey) => client.invalidateQueries({ queryKey })))
}

/** Everything that shows meals or numbers made from them. */
export const invalidateMeals = (client: QueryClient) =>
  invalidate(client, [keys.today, keys.meals, ['meal'], keys.daily, keys.report])

/** Everything that shows weight, measurements or progress photos. */
export const invalidateBody = (client: QueryClient) =>
  invalidate(client, [keys.weights, keys.measurements, keys.photos, keys.daily, keys.report])
