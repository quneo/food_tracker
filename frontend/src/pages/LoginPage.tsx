import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Loader2, Send } from 'lucide-react'
import { authApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useAuth } from '@/hooks/useAuth'
import { takeLaunch } from '@/lib/telegram'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { LeafMark } from '@/components/shared/LeafMark'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import type { LoginRequest, TelegramWidgetUser, User } from '@/types'

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramWidgetUser) => void
  }
}

type BotLogin =
  | { step: 'idle' }
  | { step: 'starting' }
  | { step: 'waiting'; request: LoginRequest; deadline: number }
  | { step: 'rejected' }
  | { step: 'expired' }

export default function LoginPage() {
  const { signedIn, launchError } = useAuth()
  const [error, setError] = useState(launchError)
  const config = useQuery({
    queryKey: keys.authConfig,
    queryFn: ({ signal }) => authApi.config({ signal }),
    staleTime: Infinity,
  })
  const invite = takeLaunch().invite

  useEffect(() => {
    document.title = 'Вход — Дневник'
  }, [])

  const finish = useCallback(
    async (fallback?: User) => {
      // The session cookie is already set; /me confirms it reached the browser.
      const user = await authApi.me().catch(() => fallback ?? null)
      if (user) signedIn(user)
      else setError('Браузер не сохранил вход. Разрешите cookies для этого сайта')
    },
    [signedIn],
  )

  const widgetLogin = useCallback(
    async (user: TelegramWidgetUser) => {
      setError('')
      try {
        signedIn(await authApi.widget(user, invite))
      } catch (e) {
        setError((e as Error).message)
      }
    },
    [invite, signedIn],
  )

  return (
    <div className="mx-auto flex min-h-dvh max-w-[1100px] flex-col px-4 sm:px-7">
      <header className="flex h-[72px] items-center justify-between">
        <span className="flex items-center gap-2.5 text-[17px] font-semibold tracking-tight">
          <LeafMark />
          Дневник
        </span>
        <ThemeToggle />
      </header>
      <main className="grid flex-1 place-items-start justify-items-center pt-6 pb-16 sm:place-items-center sm:pt-0">
        <Card className="w-full max-w-[420px] gap-6 py-7">
          <CardHeader className="gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Вход</h1>
            <CardDescription className="text-[15px]">
              Дневник питания, веса и замеров. Вход через ваш Telegram — без паролей.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {error && (
              <p
                role="alert"
                className="rounded-[14px] bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                {error}
              </p>
            )}
            <BotLoginBlock onConfirmed={finish} onError={setError} />
            {config.data?.widget && (
              <>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  или
                  <span className="h-px flex-1 bg-border" />
                </div>
                <TelegramWidget botUsername={config.data.bot_username} onAuth={widgetLogin} />
              </>
            )}
            {invite && (
              <p className="text-sm text-muted-foreground">Приглашение будет учтено при входе.</p>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  )
}

function BotLoginBlock({
  onConfirmed,
  onError,
}: {
  onConfirmed: (user?: User) => Promise<void>
  onError: (message: string) => void
}) {
  const [state, setState] = useState<BotLogin>({ step: 'idle' })
  const [now, setNow] = useState(Date.now)

  async function start() {
    onError('')
    setState({ step: 'starting' })
    try {
      const request = await authApi.startBotLogin()
      setState({ step: 'waiting', request, deadline: Date.now() + request.expires_in * 1000 })
      // Opening may be blocked after the await; the link below is always there.
      window.open(request.link, '_blank', 'noopener')
    } catch (e) {
      onError((e as Error).message)
      setState({ step: 'idle' })
    }
  }

  const waiting = state.step === 'waiting' ? state : null
  useEffect(() => {
    if (!waiting) return
    const controller = new AbortController()
    let busy = false
    const tick = async () => {
      setNow(Date.now())
      if (Date.now() > waiting.deadline) {
        setState({ step: 'expired' })
        return
      }
      if (busy) return
      busy = true
      try {
        const result = await authApi.pollBotLogin(
          waiting.request.code,
          waiting.request.poll_token,
          controller.signal,
        )
        if (result.status === 'confirmed') {
          clearInterval(timer)
          await onConfirmed(result.user)
        } else if (result.status === 'rejected') setState({ step: 'rejected' })
        else if (result.status === 'expired') setState({ step: 'expired' })
      } catch {
        /* A failed poll is retried on the next tick. */
      } finally {
        busy = false
      }
    }
    const timer = setInterval(tick, 2000)
    return () => {
      clearInterval(timer)
      controller.abort()
    }
  }, [waiting, onConfirmed])

  if (waiting) {
    const left = Math.max(0, Math.ceil((waiting.deadline - now) / 1000))
    return (
      <div className="flex flex-col gap-4" aria-live="polite">
        <div className="flex items-start gap-3 rounded-[14px] bg-accent px-4 py-3.5">
          <Loader2
            className="mt-0.5 size-5 shrink-0 animate-spin text-accent-foreground"
            aria-hidden="true"
          />
          <div className="text-sm">
            <p className="font-medium">Подтвердите вход в чате с ботом</p>
            <p className="text-muted-foreground">
              Нажмите «Старт» и подтвердите вход. Ссылка действует еще{' '}
              <span className="tabular">
                {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
              </span>
              .
            </p>
          </div>
        </div>
        <Button asChild size="lg" className="h-12">
          <a href={waiting.request.link} target="_blank" rel="noopener noreferrer">
            <ExternalLink />
            Открыть Telegram
          </a>
        </Button>
        <Button variant="ghost" onClick={() => setState({ step: 'idle' })}>
          Отмена
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {state.step === 'rejected' && (
        <p role="alert" className="text-sm text-destructive">
          Вход отклонен в Telegram.
        </p>
      )}
      {state.step === 'expired' && (
        <p role="alert" className="text-sm text-muted-foreground">
          Время на подтверждение вышло. Попробуйте еще раз.
        </p>
      )}
      <Button
        size="lg"
        className="h-12 text-[15px]"
        onClick={start}
        disabled={state.step === 'starting'}
      >
        {state.step === 'starting' ? <Loader2 className="animate-spin" /> : <Send />}
        {state.step === 'idle' || state.step === 'starting'
          ? 'Войти через Telegram'
          : 'Попробовать снова'}
      </Button>
    </div>
  )
}

/** The official Telegram Login Widget; if its script does not load, it simply is not shown. */
function TelegramWidget({
  botUsername,
  onAuth,
}: {
  botUsername: string
  onAuth: (user: TelegramWidgetUser) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const handler = useRef(onAuth)
  const [failed, setFailed] = useState(false)
  handler.current = onAuth

  useEffect(() => {
    const element = box.current
    if (!element) return
    window.onTelegramAuth = (user) => handler.current(user)
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.async = true
    script.setAttribute('data-telegram-login', botUsername)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '12')
    script.setAttribute('data-onauth', 'onTelegramAuth(user)')
    script.onerror = () => setFailed(true)
    element.appendChild(script)
    return () => {
      element.replaceChildren()
      delete window.onTelegramAuth
    }
  }, [botUsername])

  return <div ref={box} className={failed ? 'hidden' : 'flex min-h-10 justify-center'} />
}
