import { useSearchParams } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { bodyApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader } from '@/components/shared/PageHeader'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { PhotoAlbum } from '@/components/progress/PhotoAlbum'
import { CompareView } from '@/components/progress/CompareView'
import { BodySection } from '@/components/progress/BodySection'
import { PhotoLockBar } from '@/components/progress/PhotoLockBar'

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
    enabled: tab === 'compare',
  })
  const entries = useQuery({
    queryKey: keys.entries,
    queryFn: ({ signal }) => bodyApi.entries({ signal }),
    enabled: tab === 'photos',
  })

  function loaded<T>(result: UseQueryResult<T>, render: (data: T) => ReactNode) {
    return result.isPending ? (
      <BlockSkeleton rows={3} />
    ) : result.isError ? (
      <ErrorState error={result.error} retry={() => result.refetch()} />
    ) : (
      render(result.data)
    )
  }

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
        {tab !== 'body' && <PhotoLockBar />}
        <TabsContent value="photos">
          {loaded(entries, (list) => (
            <PhotoAlbum entries={list} />
          ))}
        </TabsContent>
        <TabsContent value="compare">
          {loaded(photos, (list) => (
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
