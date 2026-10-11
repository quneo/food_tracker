import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, ShieldCheck, Ticket, Trash2, UserCheck, UserX } from 'lucide-react'
import { toast } from 'sonner'
import { adminApi, authApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useUser } from '@/hooks/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, ErrorState } from '@/components/shared/States'
import { num, parseNumber, utcLabel } from '@/lib/format'
import type { AdminUser, Invite } from '@/types'

const RUNNERS: Record<string, string> = {
  ssh: 'на VPS по SSH',
  local: 'на этом сервере',
  off: 'выключен',
}

function copy(text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success('Ссылка скопирована'))
    .catch(() => toast.error('Не удалось скопировать. Выделите ссылку вручную'))
}

export function AdminSection() {
  const config = useQuery({
    queryKey: keys.authConfig,
    queryFn: ({ signal }) => authApi.config({ signal }),
    staleTime: Infinity,
  })
  const bastion = config.data?.registration === 'bastion'
  return (
    <div className="flex flex-col gap-4">
      <AiStatusCard />
      {bastion ? (
        <Card>
          <CardHeader>
            <CardTitle>Доступ</CardTitle>
            <CardDescription>
              Кто может войти, решает Bastion: доступ получают люди из групп проекта. Новые люди
              входят на сайте и сами привязывают Telegram в профиле. Если человека убрать из группы,
              в течение часа его вход и бот закроются.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        config.data && <InvitesCard />
      )}
      <UsersCard />
    </div>
  )
}

function AiStatusCard() {
  const status = useQuery({
    queryKey: [...keys.admin, 'ai'],
    queryFn: ({ signal }) => adminApi.ai({ signal }),
    refetchInterval: 30_000,
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ассистент за сутки</CardTitle>
        <CardDescription>Только счетчики и время ответа, без содержимого.</CardDescription>
      </CardHeader>
      <CardContent>
        {status.isPending ? (
          <BlockSkeleton rows={1} />
        ) : status.isError ? (
          <ErrorState error={status.error} retry={() => status.refetch()} />
        ) : (
          <div className="flex flex-col gap-3">
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: 'Запуск', value: RUNNERS[status.data.runner] ?? status.data.runner },
                { label: 'В очереди', value: num(status.data.queued) },
                {
                  label: 'Готово / ошибок',
                  value: `${num(status.data.done)} / ${num(status.data.failed)}`,
                },
                {
                  label: 'Среднее время',
                  value:
                    status.data.average_ms === null
                      ? '—'
                      : `${num(status.data.average_ms / 1000, 1)} с`,
                },
              ].map((item) => (
                <div key={item.label} className="rounded-[14px] bg-muted px-3 py-2.5">
                  <dt className="text-xs text-muted-foreground">{item.label}</dt>
                  <dd className="font-semibold">{item.value}</dd>
                </div>
              ))}
            </dl>
            {status.data.last_error && (
              <p className="text-sm text-destructive">Последняя ошибка: {status.data.last_error}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function inviteState(invite: Invite) {
  if (invite.revoked) return { label: 'отозвано', tone: 'secondary' as const }
  if (invite.usable) return { label: 'действует', tone: 'default' as const }
  if (invite.uses >= invite.max_uses) return { label: 'использовано', tone: 'secondary' as const }
  return { label: 'истекло', tone: 'secondary' as const }
}

function InvitesCard() {
  const client = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<Invite | null>(null)
  const invites = useQuery({
    queryKey: [...keys.admin, 'invites'],
    queryFn: ({ signal }) => adminApi.invites({ signal }),
  })
  const revoke = useMutation({
    mutationFn: (id: number) => adminApi.revokeInvite(id),
    onSuccess: () => client.invalidateQueries({ queryKey: [...keys.admin, 'invites'] }),
    meta: { silent: true },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Приглашения</CardTitle>
        <CardDescription>
          Ссылка открывает бота и пускает нового человека в дневник.
        </CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <Plus />
            Создать
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {invites.isPending ? (
          <BlockSkeleton rows={2} />
        ) : invites.isError ? (
          <ErrorState error={invites.error} retry={() => invites.refetch()} />
        ) : !invites.data.length ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Ticket className="size-4" aria-hidden="true" />
            Приглашений пока нет.
          </p>
        ) : (
          <ul className="row-list -mx-2">
            {invites.data.map((invite) => {
              const state = inviteState(invite)
              return (
                <li key={invite.id} className="flex items-center gap-2 px-2 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{invite.note || 'Без заметки'}</span>
                      <Badge variant={state.tone} className="font-normal">
                        {state.label}
                      </Badge>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {invite.uses} из {invite.max_uses} ·{' '}
                      {invite.expires_at ? `до ${utcLabel(invite.expires_at, false)}` : 'бессрочно'}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">{invite.link}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => copy(invite.link)}
                    aria-label="Скопировать ссылку"
                  >
                    <Copy />
                  </Button>
                  {!invite.revoked && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => setRevoking(invite)}
                      aria-label="Отозвать приглашение"
                    >
                      <Trash2 />
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
      <ResponsiveSheet open={creating} onOpenChange={setCreating} title="Новое приглашение">
        {creating && <InviteForm onDone={() => setCreating(false)} />}
      </ResponsiveSheet>
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(value) => !value && setRevoking(null)}
        title="Отозвать приглашение?"
        description="По ссылке больше нельзя будет присоединиться. Уже вошедшие останутся."
        confirmLabel="Отозвать"
        onConfirm={() => revoke.mutateAsync(revoking!.id)}
      />
    </Card>
  )
}

function InviteForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const [note, setNote] = useState('')
  const [uses, setUses] = useState('1')
  const [daysText, setDaysText] = useState('14')
  const [created, setCreated] = useState<Invite | null>(null)
  const [error, setError] = useState('')
  const create = useMutation({
    mutationFn: () => {
      const maxUses = parseNumber(uses)
      if (maxUses === null || maxUses < 1 || maxUses > 100)
        throw new Error('Использований: от 1 до 100')
      const days = daysText.trim() ? parseNumber(daysText) : null
      if (days !== null && (days < 1 || days > 365))
        throw new Error('Срок: от 1 до 365 дней или пусто')
      return adminApi.createInvite({
        note: note.trim() || null,
        max_uses: Math.round(maxUses),
        days: days === null ? null : Math.round(days),
      })
    },
    onMutate: () => setError(''),
    onSuccess: async (invite) => {
      setCreated(invite)
      await client.invalidateQueries({ queryKey: [...keys.admin, 'invites'] })
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })
  if (created)
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm">Отправьте ссылку человеку — она откроет бота и пустит в дневник.</p>
        <div className="flex items-center gap-2 rounded-[14px] bg-muted p-2 pl-3">
          <code className="min-w-0 flex-1 truncate text-sm">{created.link}</code>
          <Button
            variant="outline"
            size="icon"
            onClick={() => copy(created.link)}
            aria-label="Скопировать ссылку"
          >
            <Copy />
          </Button>
        </div>
        <Button onClick={onDone}>Готово</Button>
      </div>
    )
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-note">Для кого</Label>
        <Input
          id="invite-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={200}
          placeholder="Например, Даша"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor="invite-uses">Использований</Label>
          <Input
            id="invite-uses"
            value={uses}
            onChange={(event) => setUses(event.target.value)}
            inputMode="numeric"
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="invite-days">Действует, дней</Label>
          <Input
            id="invite-days"
            value={daysText}
            onChange={(event) => setDaysText(event.target.value)}
            inputMode="numeric"
            placeholder="бессрочно"
          />
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={create.isPending}>
        {create.isPending ? 'Создаем…' : 'Создать ссылку'}
      </Button>
    </form>
  )
}

function UsersCard() {
  const me = useUser()
  const client = useQueryClient()
  const [blocking, setBlocking] = useState<AdminUser | null>(null)
  const [deleting, setDeleting] = useState<AdminUser | null>(null)
  const users = useQuery({
    queryKey: [...keys.admin, 'users'],
    queryFn: ({ signal }) => adminApi.users({ signal }),
  })
  const refresh = () => client.invalidateQueries({ queryKey: [...keys.admin, 'users'] })
  const block = useMutation({
    mutationFn: (user: AdminUser) => adminApi.setBlocked(user.id, !user.is_blocked),
    onSuccess: refresh,
    meta: { silent: true },
  })
  const remove = useMutation({
    mutationFn: (id: number) => adminApi.removeUser(id),
    onSuccess: () => toast.success('Пользователь удален'),
    // The list is reloaded even after an error: the account may be gone already.
    onSettled: refresh,
    meta: { silent: true },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Пользователи</CardTitle>
        <CardDescription>Видны только имена и счетчики — не записи и не фото.</CardDescription>
      </CardHeader>
      <CardContent>
        {users.isPending ? (
          <BlockSkeleton rows={2} />
        ) : users.isError ? (
          <ErrorState error={users.error} retry={() => users.refetch()} />
        ) : (
          <ul className="row-list -mx-2">
            {users.data.map((user) => (
              <li key={user.id} className="flex items-center gap-2 px-2 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{user.name}</span>
                    {user.login && (
                      <span className="text-sm text-muted-foreground">{user.login}</span>
                    )}
                    {!user.telegram && <Badge variant="secondary">без Telegram</Badge>}
                    {!user.bastion_active && (
                      <Badge variant="secondary">нет доступа в Bastion</Badge>
                    )}
                    {user.username && (
                      <span className="text-sm text-muted-foreground">@{user.username}</span>
                    )}
                    {user.is_admin && (
                      <Badge variant="secondary" className="gap-1 font-normal">
                        <ShieldCheck />
                        админ
                      </Badge>
                    )}
                    {user.is_blocked && (
                      <Badge
                        variant="outline"
                        className="border-destructive/40 font-normal text-destructive"
                      >
                        заблокирован
                      </Badge>
                    )}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    записей: {num(user.meals)} · был {utcLabel(user.last_seen_at)}
                  </p>
                </div>
                {user.id !== me.id && (
                  <>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setBlocking(user)}
                      aria-label={
                        user.is_blocked
                          ? `Разблокировать ${user.name}`
                          : `Заблокировать ${user.name}`
                      }
                      title={user.is_blocked ? 'Разблокировать' : 'Заблокировать'}
                    >
                      {user.is_blocked ? <UserCheck /> : <UserX />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => setDeleting(user)}
                      aria-label={`Удалить ${user.name}`}
                      title="Удалить"
                    >
                      <Trash2 />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <ConfirmDialog
        open={blocking !== null}
        onOpenChange={(value) => !value && setBlocking(null)}
        title={
          blocking?.is_blocked
            ? `Разблокировать ${blocking?.name}?`
            : `Заблокировать ${blocking?.name}?`
        }
        description={
          blocking?.is_blocked
            ? 'Человек снова сможет войти и пользоваться ботом.'
            : 'Все сессии закроются, бот перестанет отвечать. Данные сохранятся.'
        }
        confirmLabel={blocking?.is_blocked ? 'Разблокировать' : 'Заблокировать'}
        destructive={!blocking?.is_blocked}
        onConfirm={() => block.mutateAsync(blocking!)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(value) => !value && setDeleting(null)}
        title={`Удалить ${deleting?.name}?`}
        description="Аккаунт и все его данные удалятся без возможности восстановления."
        onConfirm={() => remove.mutateAsync(deleting!.id)}
      />
    </Card>
  )
}
