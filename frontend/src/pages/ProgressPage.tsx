import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { bodyApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader } from '@/components/shared/PageHeader'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { PhotoAlbum } from '@/components/progress/PhotoAlbum'
import { CompareView } from '@/components/progress/CompareView'
import { BodySection } from '@/components/progress/BodySection'

const TABS = [
  { value: 'photos', label: 'Фото' },
  { value: 'compare', label: 'Сравнение' },
  { value: 'body', label: 'Замеры' },
]

export default function ProgressPage() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.some((item) => item.value === params.get('tab')) ? params.get('tab')! : 'photos'
  const photos = useQuery({
    queryKey: keys.photos,
    queryFn: ({ signal }) => bodyApi.photos({ signal }),
  })

  const gallery = (render: (list: NonNullable<typeof photos.data>) => React.ReactNode) =>
    photos.isPending ? (
      <BlockSkeleton rows={3} />
    ) : photos.isError ? (
      <ErrorState error={photos.error} retry={() => photos.refetch()} />
    ) : (
      render(photos.data)
    )

  return (
    <>
      <PageHeader title="Прогресс" />
      <Tabs
        value={tab}
        onValueChange={(value) => {
          const next = new URLSearchParams(params)
          next.set('tab', value)
          setParams(next, { replace: true })
        }}
        className="gap-5"
      >
        <TabsList className="w-full sm:w-fit">
          {TABS.map((item) => (
            <TabsTrigger key={item.value} value={item.value} className="flex-1 sm:flex-none">
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="photos">
          {gallery((list) => (
            <PhotoAlbum photos={list} />
          ))}
        </TabsContent>
        <TabsContent value="compare">
          {gallery((list) => (
            <CompareView photos={list} />
          ))}
        </TabsContent>
        <TabsContent value="body">
          <BodySection />
        </TabsContent>
      </Tabs>
    </>
  )
}
