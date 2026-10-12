import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { bodyApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader } from '@/components/shared/PageHeader'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { NewEntrySheet, PhotoAlbum } from '@/components/progress/PhotoAlbum'
import { CompareView } from '@/components/progress/CompareView'
import { BodySection } from '@/components/progress/BodySection'
import { PhotoLockButton } from '@/components/progress/PhotoLock'
import type { ProgressEntry } from '@/types'

const TABS = [
  { value: 'photos', label: 'Фото' },
  { value: 'compare', label: 'Сравнение' },
  { value: 'body', label: 'Замеры' },
]

export default function ProgressPage() {
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const tab = TABS.some((item) => item.value === params.get('tab')) ? params.get('tab')! : 'photos'
  const entries = useQuery({
    queryKey: keys.entries,
    queryFn: ({ signal }) => bodyApi.entries({ signal }),
    enabled: tab !== 'body',
  })

  const loaded = (render: (list: ProgressEntry[]) => ReactNode) =>
    entries.isPending ? (
      <BlockSkeleton rows={3} />
    ) : entries.isError ? (
      <ErrorState error={entries.error} retry={() => entries.refetch()} />
    ) : (
      render(entries.data)
    )

  return (
    <>
      <PageHeader title="Прогресс">
        {tab !== 'body' && <PhotoLockButton />}
        {tab === 'photos' && (
          <Button
            onClick={() => setCreating(true)}
            className="max-sm:w-11 max-sm:px-0"
            aria-label="Новая запись"
          >
            <Plus />
            <span className="max-sm:sr-only">Новая запись</span>
          </Button>
        )}
      </PageHeader>
      <Tabs
        value={tab}
        onValueChange={(value) => {
          const next = new URLSearchParams(params)
          next.set('tab', value)
          setParams(next, { replace: true })
        }}
        className="gap-4"
      >
        <TabsList className="w-full sm:w-fit">
          {TABS.map((item) => (
            <TabsTrigger key={item.value} value={item.value} className="flex-1 sm:flex-none">
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="photos" className="max-w-[820px]">
          {loaded((list) => (
            <PhotoAlbum entries={list} onCreate={() => setCreating(true)} />
          ))}
        </TabsContent>
        <TabsContent value="compare" className="max-w-[820px]">
          {loaded((list) => (
            <CompareView entries={list} />
          ))}
        </TabsContent>
        <TabsContent value="body">
          <BodySection />
        </TabsContent>
      </Tabs>
      <NewEntrySheet open={creating} onOpenChange={setCreating} />
    </>
  )
}
