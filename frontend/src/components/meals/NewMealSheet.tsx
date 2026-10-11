import { toast } from 'sonner'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { MealEditor } from './MealEditor'
import { useMealParam } from './MealSheet'

export function NewMealSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { open: openMeal } = useMealParam()
  return (
    <ResponsiveSheet open={open} onOpenChange={onOpenChange} title="Новая запись" wide>
      {open && (
        <MealEditor
          onDone={() => onOpenChange(false)}
          onCreated={(meal) =>
            toast.success('Запись добавлена', {
              action: { label: 'Добавить фото', onClick: () => openMeal(meal.id) },
            })
          }
        />
      )}
    </ResponsiveSheet>
  )
}
