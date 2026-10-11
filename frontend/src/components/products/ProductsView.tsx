import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImagePlus, Plus, Search, Tag, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { productsApi } from '@/api/endpoints'
import { invalidateMeals, keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Photo } from '@/components/shared/Photo'
import { Lightbox } from '@/components/shared/Lightbox'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { MacroLine } from '@/components/meals/MealBits'
import { PHOTO_TYPES } from '@/components/meals/MealPhotos'
import { inputNumber, num, parseNumber, plural } from '@/lib/format'
import type { Product, ProductIn } from '@/types'

const MAX_PHOTOS = 4

/** «Мои продукты»: the person's own milk, bars, yogurts with numbers from their labels. */
export function ProductsView() {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<number | 'new' | null>(null)
  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])
  const products = useQuery({
    queryKey: [...keys.products, q],
    queryFn: ({ signal }) => productsApi.list(q || null, { signal }),
  })
  const list = products.data ?? []
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Найти продукт"
            aria-label="Найти продукт"
            className="rounded-full pl-10"
          />
        </div>
        <Button onClick={() => setOpen('new')}>
          <Plus />
          Добавить продукт
        </Button>
      </div>

      {products.isPending ? (
        <BlockSkeleton rows={3} />
      ) : products.isError ? (
        <ErrorState error={products.error} retry={() => products.refetch()} />
      ) : !list.length ? (
        <div className="glass rounded-[24px]">
          <EmptyState
            icon={Tag}
            title={q ? 'Ничего не нашлось' : 'Своих продуктов пока нет'}
            description={
              q
                ? 'Попробуйте другое слово.'
                : 'Пришлите боту фото этикетки с подписью «запомни мое молоко» — он сохранит КБЖУ и фото состава. Или добавьте продукт здесь.'
            }
          />
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 min-[1180px]:grid-cols-3">
          {list.map((product) => (
            <li key={product.id}>
              <ProductCard product={product} onOpen={() => setOpen(product.id)} />
            </li>
          ))}
        </ul>
      )}

      <ProductSheet
        product={typeof open === 'number' ? (list.find((p) => p.id === open) ?? null) : null}
        open={open !== null}
        onOpenChange={(value) => !value && setOpen(null)}
        onCreated={(product) => setOpen(product.id)}
      />
    </div>
  )
}

function ProductCard({ product, onOpen }: { product: Product; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="glass flex h-full w-full items-center gap-3.5 rounded-[22px] p-3 text-left transition-colors hover:bg-card"
    >
      {product.photos[0] ? (
        <Photo id={product.photos[0].id} alt="" className="size-16 shrink-0 rounded-[16px]" />
      ) : (
        <span
          className="chat-avatar is-empty size-16 rounded-[16px]"
          aria-hidden="true"
          style={{ borderRadius: 16 }}
        >
          <Tag className="size-5" />
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate font-medium">{product.name}</span>
        <span className="text-sm">
          <span className="serif-number">{num(product.kcal)}</span>{' '}
          <span className="text-muted-foreground">ккал на 100 г</span>
        </span>
        <MacroLine value={product} className="text-[13px] text-muted-foreground" />
        {(product.portion_grams || product.uses > 0) && (
          <span className="truncate text-xs text-muted-foreground">
            {product.portion_grams
              ? `${product.portion_name ?? 'порция'} ${num(product.portion_grams)} г`
              : ''}
            {product.portion_grams && product.uses > 0 ? ', ' : ''}
            {product.uses > 0
              ? `в записях ${product.uses} ${plural(product.uses, ['раз', 'раза', 'раз'])}`
              : ''}
          </span>
        )}
      </span>
    </button>
  )
}

type Draft = Record<
  | 'name'
  | 'brand'
  | 'kcal'
  | 'protein'
  | 'fat'
  | 'carbs'
  | 'portion_name'
  | 'portion_grams'
  | 'package_grams'
  | 'comment',
  string
>

const toDraft = (product: Product | null): Draft => ({
  name: product?.name ?? '',
  brand: product?.brand ?? '',
  kcal: inputNumber(product?.kcal),
  protein: inputNumber(product?.protein),
  fat: inputNumber(product?.fat),
  carbs: inputNumber(product?.carbs),
  portion_name: product?.portion_name ?? '',
  portion_grams: inputNumber(product?.portion_grams),
  package_grams: inputNumber(product?.package_grams),
  comment: product?.comment ?? '',
})

const NUMBERS: { field: keyof Draft; label: string; max: number }[] = [
  { field: 'kcal', label: 'Ккал', max: 900 },
  { field: 'protein', label: 'Белки, г', max: 100 },
  { field: 'fat', label: 'Жиры, г', max: 100 },
  { field: 'carbs', label: 'Углеводы, г', max: 100 },
]

/** -> values for the API, or the first problem as a message. */
function toValues(draft: Draft): ProductIn | string {
  if (!draft.name.trim()) return 'Напишите название'
  const values: Record<string, number | null> = {}
  for (const { field, label, max } of NUMBERS) {
    const value = parseNumber(draft[field])
    if (draft[field].trim() && value === null) return `Проверьте поле «${label}»`
    if (value !== null && (value < 0 || value > max)) return `«${label}» на 100 г: от 0 до ${max}`
    values[field] = value
  }
  if (values.kcal === null) return 'Укажите калории на 100 г'
  const portion = parseNumber(draft.portion_grams)
  const pack = parseNumber(draft.package_grams)
  if (draft.portion_grams.trim() && (portion === null || portion <= 0))
    return 'Проверьте вес порции'
  if (draft.package_grams.trim() && (pack === null || pack <= 0)) return 'Проверьте вес упаковки'
  return {
    name: draft.name.trim(),
    brand: draft.brand.trim() || null,
    kcal: values.kcal!,
    protein: values.protein ?? 0,
    fat: values.fat ?? 0,
    carbs: values.carbs ?? 0,
    portion_name: draft.portion_name.trim() || null,
    portion_grams: portion,
    package_grams: pack,
    comment: draft.comment.trim() || null,
  }
}

function ProductSheet({
  product,
  open,
  onOpenChange,
  onCreated,
}: {
  product: Product | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (product: Product) => void
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useState<Draft>(() => toDraft(product))
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)
  useEffect(() => {
    if (open) {
      setDraft(toDraft(product))
      setError('')
    }
  }, [open, product])

  const refresh = () => client.invalidateQueries({ queryKey: keys.products })
  const save = useMutation({
    mutationFn: (values: ProductIn) =>
      product ? productsApi.update(product.id, values) : productsApi.create(values),
    onSuccess: async (saved) => {
      await refresh()
      await invalidateMeals(client)
      if (product) {
        toast.success('Продукт сохранен')
        onOpenChange(false)
      } else {
        toast.success('Продукт добавлен. Можно добавить фото этикетки')
        onCreated(saved)
      }
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })
  const remove = useMutation({
    mutationFn: () => productsApi.remove(product!.id),
    onSuccess: async () => {
      toast.success('Продукт удален')
      onOpenChange(false)
      await refresh()
    },
  })

  const set = (field: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft((current) => ({ ...current, [field]: event.target.value }))

  return (
    <ResponsiveSheet
      open={open}
      onOpenChange={onOpenChange}
      title={product ? product.name : 'Новый продукт'}
      description="Значения на 100 г (или 100 мл), как на этикетке."
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          const values = toValues(draft)
          if (typeof values === 'string') setError(values)
          else {
            setError('')
            save.mutate(values)
          }
        }}
      >
        {product && <ProductPhotos product={product} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="product-name">Название</Label>
            <Input
              id="product-name"
              value={draft.name}
              onChange={set('name')}
              placeholder="Молоко 2,5%"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="product-brand">Бренд</Label>
            <Input id="product-brand" value={draft.brand} onChange={set('brand')} />
          </div>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">На 100 г</legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {NUMBERS.map(({ field, label }) => (
              <div key={field} className="flex flex-col gap-1.5">
                <Label htmlFor={`product-${field}`} className="text-xs text-muted-foreground">
                  {label}
                </Label>
                <Input
                  id={`product-${field}`}
                  inputMode="decimal"
                  value={draft[field]}
                  onChange={set(field)}
                  className="tabular"
                />
              </div>
            ))}
          </div>
        </fieldset>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="product-portion-name" className="text-xs text-muted-foreground">
              Порция
            </Label>
            <Input
              id="product-portion-name"
              value={draft.portion_name}
              onChange={set('portion_name')}
              placeholder="стакан"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="product-portion-grams" className="text-xs text-muted-foreground">
              Вес порции, г
            </Label>
            <Input
              id="product-portion-grams"
              inputMode="decimal"
              value={draft.portion_grams}
              onChange={set('portion_grams')}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="product-package" className="text-xs text-muted-foreground">
              Упаковка, г
            </Label>
            <Input
              id="product-package"
              inputMode="decimal"
              value={draft.package_grams}
              onChange={set('package_grams')}
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="product-comment">Комментарий</Label>
          <Textarea
            id="product-comment"
            rows={2}
            value={draft.comment}
            onChange={set('comment')}
            placeholder="Где покупаю, вкус, на что похоже"
          />
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          {product ? (
            <Button
              type="button"
              variant="ghost"
              className="text-destructive"
              onClick={() => setDeleting(true)}
            >
              <Trash2 />
              Удалить
            </Button>
          ) : (
            <span />
          )}
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? 'Сохраняем…' : product ? 'Сохранить' : 'Добавить'}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Удалить продукт?"
        description="Продукт и фото этикетки удалятся. Записи, где он использован, останутся."
        onConfirm={() => remove.mutateAsync()}
      />
    </ResponsiveSheet>
  )
}

/** Label photos: what the product is and what is in it. */
function ProductPhotos({ product }: { product: Product }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [viewing, setViewing] = useState<number | null>(null)
  const [removing, setRemoving] = useState<number | null>(null)
  const refresh = () => client.invalidateQueries({ queryKey: keys.products })
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files.slice(0, MAX_PHOTOS - product.photos.length))
        await productsApi.addPhoto(product.id, file)
    },
    onSuccess: refresh,
    onError: refresh,
  })
  const remove = useMutation({
    mutationFn: (mediaId: number) => productsApi.removePhoto(product.id, mediaId),
    onSuccess: refresh,
  })
  return (
    <div className="flex flex-wrap gap-2">
      {product.photos.map((photo, index) => (
        <div key={photo.id} className="relative">
          <button
            type="button"
            className="block overflow-hidden rounded-[14px]"
            onClick={() => setViewing(index)}
            aria-label={`Открыть фото ${index + 1}`}
          >
            <Photo id={photo.id} alt={`Фото ${index + 1}`} className="size-24 rounded-[14px]" />
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
      {product.photos.length < MAX_PHOTOS && (
        <Button
          type="button"
          variant="outline"
          className="size-24 flex-col gap-1 rounded-[14px] border-dashed text-xs font-normal text-muted-foreground"
          onClick={() => input.current?.click()}
          disabled={upload.isPending}
        >
          <ImagePlus className="size-5" />
          {upload.isPending ? 'Загрузка…' : 'Фото этикетки'}
        </Button>
      )}
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
        ids={product.photos.map((photo) => photo.id)}
        index={viewing}
        onIndexChange={setViewing}
        onClose={() => setViewing(null)}
        title={product.name}
      />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(value) => !value && setRemoving(null)}
        title="Удалить фото?"
        onConfirm={() => remove.mutateAsync(removing!)}
      />
    </div>
  )
}
