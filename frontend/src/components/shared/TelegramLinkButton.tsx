import { useEffect, useState } from 'react'
import { Copy, ExternalLink, Loader2, Send } from 'lucide-react'
import { toast } from 'sonner'
import { authApi } from '@/api/endpoints'
import { useAuth } from '@/hooks/useAuth'
import { copyText } from '@/lib/clipboard'
import { botLink } from '@/lib/telegram'
import { Button } from '@/components/ui/button'
import type { TelegramLink } from '@/types'

/** Links the signed-in account to the person's Telegram: a one-time key is sent to the bot
 * as "/link <key>", and this block notices the link by re-reading /me. */
export function TelegramLinkButton({ className }: { className?: string }) {
  const { signedIn } = useAuth()
  const [key, setKey] = useState<(TelegramLink & { deadline: number }) | null>(null)
  const [starting, setStarting] = useState(false)
  const [now, setNow] = useState(Date.now)

  async function start() {
    setStarting(true)
    try {
      const created = await authApi.telegramLink()
      setKey({ ...created, deadline: Date.now() + created.expires_in * 1000 })
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (!key) return
    const timer = setInterval(async () => {
      setNow(Date.now())
      if (Date.now() > key.deadline) return
      try {
        const me = await authApi.me()
        if (me.telegram_id) {
          setKey(null)
          signedIn(me)
          toast.success('Telegram привязан')
        }
      } catch {
        /* Retried on the next tick. */
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [key, signedIn])

  if (key) {
    const left = Math.max(0, Math.ceil((key.deadline - now) / 1000))
    const expired = left === 0
    return (
      <div className={className} aria-live="polite">
        <div className="flex flex-col gap-3 rounded-[14px] bg-accent px-4 py-3.5 text-sm">
          {expired ? (
            <p className="font-medium">Ключ истек. Получите новый.</p>
          ) : (
            <>
              <p className="font-medium">Отправьте боту @{key.bot_username} эту команду:</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-[10px] border bg-background px-3 py-2 font-mono text-[13px] select-all">
                  {key.command}
                </code>
                <Button
                  size="icon"
                  variant="outline"
                  aria-label="Скопировать команду"
                  onClick={async () => {
                    if (await copyText(key.command)) toast.success('Команда скопирована')
                    else toast.error('Не получилось скопировать — выделите команду вручную')
                  }}
                >
                  <Copy />
                </Button>
              </div>
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden="true" />
                Ждем привязку · ключ действует еще{' '}
                <span className="tabular">
                  {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
                </span>
              </p>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            {expired ? (
              <Button size="sm" onClick={start} disabled={starting}>
                {starting ? <Loader2 className="animate-spin" /> : <Send />}
                Новый ключ
              </Button>
            ) : (
              <Button asChild size="sm">
                <a href={botLink(key.bot_username)} target="_blank" rel="noopener noreferrer">
                  <ExternalLink />
                  Открыть бота
                </a>
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setKey(null)}>
              Отмена
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <Button className={className} onClick={start} disabled={starting}>
      {starting ? <Loader2 className="animate-spin" /> : <Send />}
      Привязать Telegram
    </Button>
  )
}
