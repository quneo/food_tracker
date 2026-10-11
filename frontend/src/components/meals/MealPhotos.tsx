import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ImagePlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { mealsApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Photo } from '@/components/shared/Photo'
import { Lightbox } from '@/components/shared/Lightbox'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import type { Meal } from '@/types'

const MAX_PHOTOS = 6
export const PHOTO_TYPES = 'image/jpeg,image/png,image/webp'

/** `compact`: without photos, a small button instead of an empty tile. */
export function MealPhotos({ meal, compact = false }: { meal: Meal; compact?: boolean }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [viewing, setViewing] = useState<number | null>(null)
  const [removing, setRemoving] = useState<number | null>(null)

  const saved = (value: Meal) => {
    client.setQueryData(keys.meal(value.id), value)
    return invalidateMeals(client)
  }
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      let last: Meal | null = null
      for (const file of files.slice(0, MAX_PHOTOS - meal.photos.length))
        last = await mealsApi.addPhoto(meal.id, file)
      return last
    },
    onSuccess: (value) => {
      if (!value) return
      toast.success('Фото добавлено')
      return saved(value)
    },
  })
  const remove = useMutation({
    mutationFn: (mediaId: number) => mealsApi.removePhoto(meal.id, mediaId),
    onSuccess: saved,
    onError: () => invalidateMeals(client),
    meta: { silent: true },
  })

  const ids = meal.photos.map((photo) => photo.id)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {meal.photos.map((photo, index) => (
          <div key={photo.id} className="relative">
            <button
              type="button"
              className="block overflow-hidden rounded-[14px]"
              onClick={() => setViewing(index)}
              aria-label={`Открыть фото ${index + 1}`}
            >
              <Photo
                id={photo.id}
                alt={`Фото ${index + 1}`}
                className="size-24 rounded-[14px] sm:size-28"
              />
            </button>
            <button
              type="button"
              className="absolute -top-1.5 -right-1.5 grid size-8 place-items-center rounded-full border bg-card text-muted-foreground shadow-sm hover:text-destructive"
              onClick={() => setRemoving(photo.id)}
              aria-label={`Удалить фото ${index + 1}`}
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
        {compact && meal.photos.length === 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-ml-2 text-muted-foreground"
            onClick={() => input.current?.click()}
            disabled={upload.isPending}
          >
            <ImagePlus />
            {upload.isPending ? 'Загрузка…' : 'Добавить фото'}
          </Button>
        ) : (
          meal.photos.length < MAX_PHOTOS && (
            <Button
              type="button"
              variant="outline"
              className="size-24 flex-col gap-1 rounded-[14px] border-dashed text-xs font-normal text-muted-foreground sm:size-28"
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
            >
              <ImagePlus className="size-5" />
              {upload.isPending ? 'Загрузка…' : 'Добавить фото'}
            </Button>
          )
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES}
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          event.target.value = ''
          if (files.length) upload.mutate(files)
        }}
      />
      <Lightbox
        ids={ids}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title={meal.title}
      />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(value) => !value && setRemoving(null)}
        title="Удалить фото?"
        description="Фото удалится из записи и хранилища."
        onConfirm={() => remove.mutateAsync(removing!)}
      />
    </div>
  )
}
