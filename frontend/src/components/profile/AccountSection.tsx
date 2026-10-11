import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LogOut, MonitorSmartphone, Send, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { authApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useAuth, useUser } from '@/hooks/useAuth'
import { useTheme, type ThemePreference } from '@/hooks/useTheme'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { TelegramLinkButton } from '@/components/shared/TelegramLinkButton'
import { botLink } from '@/lib/telegram'
import { utcLabel } from '@/lib/format'

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Как в системе' },
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Темная' },
]

export function AccountSection() {
  const user = useUser()
  const { logout, forget } = useAuth()
  const { preference, setTheme } = useTheme()
  const [everywhere, setEverywhere] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const config = useQuery({
    queryKey: keys.authConfig,
    queryFn: ({ signal }) => authApi.config({ signal }),
    staleTime: Infinity,
  })

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Аккаунт</CardTitle>
          <CardDescription>
            {user.bastion
              ? 'Вход через Bastion. Еду, вес и вопросы удобнее всего присылать боту в Telegram.'
              : 'Вход и данные связаны с вашим Telegram.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">{user.bastion ? 'Имя' : 'Имя в Telegram'}</dt>
              <dd className="font-medium">{user.name}</dd>
            </div>
            {user.bastion && (
              <div>
                <dt className="text-muted-foreground">Логин Bastion</dt>
                <dd className="font-medium">{user.login}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">Telegram</dt>
              <dd className="font-medium">
                {!user.telegram_id
                  ? 'не привязан'
                  : user.username
                    ? `@${user.username}`
                    : 'привязан'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">В дневнике с</dt>
              <dd className="font-medium">{utcLabel(user.created_at, false)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Часовой пояс</dt>
              <dd className="font-medium">{user.timezone}</dd>
            </div>
          </dl>
          {!user.telegram_id && <TelegramLinkButton className="self-start" />}
          {config.data && user.telegram_id && (
            <Button asChild variant="outline" className="self-start">
              <a href={botLink(config.data.bot_username)} target="_blank" rel="noopener noreferrer">
                <Send />
                Открыть бота @{config.data.bot_username}
              </a>
            </Button>
          )}
          <div className="flex flex-col gap-2">
            <span id="theme-label" className="text-sm font-medium">
              Тема
            </span>
            <div className="chips" role="radiogroup" aria-labelledby="theme-label">
              {THEMES.map((theme) => (
                <button
                  key={theme.value}
                  type="button"
                  role="radio"
                  aria-checked={preference === theme.value}
                  data-state={preference === theme.value ? 'on' : 'off'}
                  className="chip"
                  onClick={() => setTheme(theme.value)}
                >
                  {theme.label}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Выход</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => logout().catch((e) => toast.error(e.message))}>
            <LogOut />
            Выйти
          </Button>
          <Button variant="ghost" onClick={() => setEverywhere(true)}>
            <MonitorSmartphone />
            Выйти на всех устройствах
          </Button>
        </CardContent>
      </Card>

      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle>Удаление аккаунта</CardTitle>
          <CardDescription>
            Удалятся все записи, фото, замеры, память ассистента и переписка. Восстановить нельзя.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            className="border-destructive/40 text-destructive hover:text-destructive"
            onClick={() => setDeleting(true)}
          >
            <Trash2 />
            Удалить аккаунт
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={everywhere}
        onOpenChange={setEverywhere}
        title="Выйти на всех устройствах?"
        description="Сессии в браузерах и Telegram закроются; войти можно будет снова через бота."
        confirmLabel="Выйти везде"
        onConfirm={() => logout(true)}
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={(value) => {
          setDeleting(value)
          if (!value) setConfirmText('')
        }}
        title="Удалить аккаунт навсегда?"
        description="Все данные удалятся без возможности восстановления. Чтобы подтвердить, напишите «удалить»."
        confirmLabel="Удалить навсегда"
        disabled={confirmText.trim().toLowerCase() !== 'удалить'}
        onConfirm={async () => {
          try {
            await authApi.deleteAccount(confirmText.trim())
          } catch (error) {
            // The server may fail after the account is already gone (e.g. while cleaning up
            // photo storage): if the session no longer works, the deletion happened.
            if (error instanceof ApiError && error.status < 500) throw error
            if (await authApi.me().catch(() => null)) throw error
          }
          toast.success('Аккаунт удален')
          forget()
        }}
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="delete-confirm">Подтверждение</Label>
          <Input
            id="delete-confirm"
            value={confirmText}
            onChange={(event) => setConfirmText(event.target.value)}
            placeholder="удалить"
            autoComplete="off"
          />
        </div>
      </ConfirmDialog>
    </div>
  )
}
