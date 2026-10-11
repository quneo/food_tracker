import { useCallback } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { mealsApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { MealEditor } from './MealEditor'
import { MealView } from './MealView'

/**
 * The open meal lives in the address (?meal=12, and &edit=1 while it is being changed):
 * the bot links straight to it, and the back button closes it.
 */
export function useMealParam() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const raw = params.get('meal')
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null
  const editing = params.get('edit') === '1'

  const open = useCallback(
    (mealId: number, edit = false) => {
      const next = new URLSearchParams(location.search)
      next.set('meal', String(mealId))
      if (edit) next.set('edit', '1')
      else next.delete('edit')
      navigate({ search: next.toString() }, { state: { mealOpened: true } })
    },
    [location.search, navigate],
  )

  /** Between looking at the meal and changing it, without a new history entry. */
  const setEditing = useCallback(
    (value: boolean) => {
      const next = new URLSearchParams(location.search)
      if (value) next.set('edit', '1')
      else next.delete('edit')
      navigate({ search: next.toString() }, { replace: true, state: location.state })
    },
    [location.search, location.state, navigate],
  )

  const close = useCallback(() => {
    if ((location.state as { mealOpened?: boolean } | null)?.mealOpened) {
      navigate(-1)
      return
    }
    const next = new URLSearchParams(location.search)
    next.delete('meal')
    next.delete('edit')
    navigate({ search: next.toString() }, { replace: true })
  }, [location.search, location.state, navigate])

  return { id, editing, open, close, setEditing }
}

export function MealSheetHost() {
  const { id, editing, close, setEditing } = useMealParam()
  const meal = useQuery({
    queryKey: keys.meal(id ?? 0),
    queryFn: ({ signal }) => mealsApi.get(id!, { signal }),
    enabled: id !== null,
  })
  return (
    <ResponsiveSheet
      open={id !== null}
      onOpenChange={(value) => !value && close()}
      title={editing ? 'Изменить запись' : (meal.data?.title ?? 'Прием пищи')}
      wide
    >
      {meal.isPending ? (
        <BlockSkeleton rows={4} />
      ) : meal.isError ? (
        <ErrorState error={meal.error} retry={() => meal.refetch()} />
      ) : editing ? (
        <MealEditor
          key={meal.data.id}
          meal={meal.data}
          onDone={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <MealView meal={meal.data} onEdit={() => setEditing(true)} onClose={close} />
      )}
    </ResponsiveSheet>
  )
}
