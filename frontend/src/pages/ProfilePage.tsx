import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { profileApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader } from '@/components/shared/PageHeader'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { ProfileForm } from '@/components/profile/ProfileForm'
import { RemindersSection } from '@/components/profile/RemindersSection'
import { MemorySection } from '@/components/profile/MemorySection'
import { AccountSection } from '@/components/profile/AccountSection'
import { AdminSection } from '@/components/profile/AdminSection'

export default function ProfilePage() {
  const user = useUser()
  const [params, setParams] = useSearchParams()
  const sections = [
    { value: 'goals', label: 'Параметры' },
    { value: 'reminders', label: 'Напоминания' },
    { value: 'memory', label: 'AI-память' },
    { value: 'account', label: 'Аккаунт' },
    ...(user.is_admin ? [{ value: 'admin', label: 'Админ' }] : []),
  ]
  const section = sections.some((item) => item.value === params.get('section'))
    ? params.get('section')!
    : 'goals'
  const profile = useQuery({
    queryKey: keys.profile,
    queryFn: ({ signal }) => profileApi.get({ signal }),
  })

  return (
    <>
      <PageHeader
        title="Профиль"
        meta={user.username ? `${user.name} · @${user.username}` : user.name}
      >
        <span className="min-[900px]:hidden">
          <ThemeToggle />
        </span>
      </PageHeader>
      <Tabs
        value={section}
        onValueChange={(value) => {
          const next = new URLSearchParams(params)
          next.set('section', value)
          setParams(next, { replace: true })
        }}
        className="gap-5"
      >
        <TabsList className="flex h-auto w-full flex-wrap justify-start sm:w-fit">
          {sections.map((item) => (
            <TabsTrigger key={item.value} value={item.value} className="flex-none">
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="max-w-3xl">
          <TabsContent value="goals">
            {profile.isPending ? (
              <BlockSkeleton rows={5} />
            ) : profile.isError ? (
              <ErrorState error={profile.error} retry={() => profile.refetch()} />
            ) : (
              <ProfileForm profile={profile.data} />
            )}
          </TabsContent>
          <TabsContent value="reminders">
            <RemindersSection />
          </TabsContent>
          <TabsContent value="memory">
            <MemorySection />
          </TabsContent>
          <TabsContent value="account">
            <AccountSection />
          </TabsContent>
          {user.is_admin && (
            <TabsContent value="admin">
              <AdminSection />
            </TabsContent>
          )}
        </div>
      </Tabs>
    </>
  )
}
