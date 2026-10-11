import { useCallback } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { mealsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { MealEditor } from './MealEditor'

/**
 * The open meal lives in the address (?meal=12): the bot links straight to it, and the
 * back button closes it.
 */
export function useMealParam() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const raw = params.get('meal')
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null

  const open = useCallback(
    (mealId: number) => {
      const next = new URLSearchParams(location.search)
      next.set('meal', String(mealId))
      navigate({ search: next.toString() }, { state: { mealOpened: true } })
    },
    [location.search, navigate],
  )

  const close = useCallback(() => {
    if ((location.state as { mealOpened?: boolean } | null)?.mealOpened) {
      navigate(-1)
      return
    }
    const next = new URLSearchParams(location.search)
    next.delete('meal')
    navigate({ search: next.toString() }, { replace: true })
  }, [location.search, location.state, navigate])

  return { id, open, close }
}

export function MealSheetHost() {
  const { id, close } = useMealParam()
  const meal = useQuery({
    queryKey: keys.meal(id ?? 0),
    queryFn: ({ signal }) => mealsApi.get(id!, { signal }),
    enabled: id !== null,
  })
  return (
    <ResponsiveSheet
      open={id !== null}
      onOpenChange={(value) => !value && close()}
      title={meal.data?.title ?? 'Прием пищи'}
      wide
    >
      {meal.isPending ? (
        <BlockSkeleton rows={4} />
      ) : meal.isError ? (
        <ErrorState error={meal.error} retry={() => meal.refetch()} />
      ) : (
        <MealEditor key={meal.data.id} meal={meal.data} onDone={close} />
      )}
    </ResponsiveSheet>
  )
}
