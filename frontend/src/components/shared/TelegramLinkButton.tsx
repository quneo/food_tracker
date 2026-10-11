import { useEffect, useState } from 'react'
import { ExternalLink, Loader2, Send } from 'lucide-react'
import { toast } from 'sonner'
import { authApi } from '@/api/endpoints'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import type { TelegramLink } from '@/types'

/** Links the signed-in account to the person's Telegram: opens the bot, the person confirms
 * there, and this button notices it by re-reading /me. */
export function TelegramLinkButton({ className }: { className?: string }) {
  const { signedIn } = useAuth()
  const [link, setLink] = useState<(TelegramLink & { deadline: number }) | null>(null)
  const [starting, setStarting] = useState(false)

  async function start() {
    setStarting(true)
    try {
      const created = await authApi.telegramLink()
      setLink({ ...created, deadline: Date.now() + created.expires_in * 1000 })
      window.open(created.link, '_blank', 'noopener')
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (!link) return
    const timer = setInterval(async () => {
      if (Date.now() > link.deadline) {
        setLink(null)
        return
      }
      try {
        const me = await authApi.me()
        if (me.telegram_id) {
          setLink(null)
          signedIn(me)
          toast.success('Telegram привязан')
        }
      } catch {
        /* Retried on the next tick. */
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [link, signedIn])

  if (link)
    return (
      <div className={className} aria-live="polite">
        <div className="flex flex-col gap-3 rounded-[14px] bg-accent px-4 py-3.5 text-sm">
          <p className="flex items-center gap-2 font-medium">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Подтвердите привязку в чате с ботом
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <a href={link.link} target="_blank" rel="noopener noreferrer">
                <ExternalLink />
                Открыть Telegram
              </a>
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setLink(null)}>
              Отмена
            </Button>
          </div>
        </div>
      </div>
    )

  return (
    <Button className={className} onClick={start} disabled={starting}>
      {starting ? <Loader2 className="animate-spin" /> : <Send />}
      Привязать Telegram
    </Button>
  )
}
