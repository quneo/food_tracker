import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Loader2, LogIn, Send } from 'lucide-react'
import { ApiError } from '@/api/client'
import { authApi } from '@/api/endpoints'
import { keys } from '@/api/keys'
import { useAuth } from '@/hooks/useAuth'
import { takeLaunch } from '@/lib/telegram'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LeafMark } from '@/components/shared/LeafMark'
import breakfast from '@/assets/breakfast.webp'
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
        <span className="flex items-center gap-2.5 font-serif text-[21px] font-semibold">
          <LeafMark />
          Дневник
        </span>
        <ThemeToggle />
      </header>
      <main className="grid flex-1 content-start items-center justify-items-center gap-10 pt-2 pb-16 lg:grid-cols-[minmax(0,1fr)_420px] lg:content-center lg:justify-items-stretch lg:gap-16">
        <section className="flex flex-col items-center gap-5 text-center lg:items-start lg:text-left">
          <img
            src={breakfast}
            alt=""
            draggable={false}
            className="w-44 select-none sm:w-52 lg:w-[min(100%,420px)]"
          />
          <div className="hidden max-w-[460px] flex-col gap-3 lg:flex">
            <p className="font-serif text-[42px] leading-[1.08] font-semibold tracking-tight">
              Еда, вес и прогресс в одном дневнике
            </p>
            <p className="text-[17px] text-muted-foreground">
              Пишите боту в Telegram: фото тарелки или пару слов. Здесь — дни, графики и фото
              прогресса.
            </p>
          </div>
        </section>
        <Card className="w-full max-w-[420px] gap-6 py-7">
          <CardHeader className="gap-2">
            <h1 className="font-serif text-[28px] font-semibold tracking-tight">Вход</h1>
            <CardDescription className="text-[15px]">
              {config.data?.bastion
                ? 'Дневник питания, веса и замеров. Вход через Bastion: логин, пароль и код из приложения.'
                : 'Дневник питания, веса и замеров. Вход через ваш Telegram — без паролей.'}
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
            {config.data?.bastion && (
              <>
                <BastionForm bastionUrl={config.data.bastion_url} onSignedIn={signedIn} />
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  или, если Telegram уже привязан
                  <span className="h-px flex-1 bg-border" />
                </div>
              </>
            )}
            <BotLoginBlock
              onConfirmed={finish}
              onError={setError}
              secondary={Boolean(config.data?.bastion)}
            />
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

/** Bastion's own sign-in form: the backend checks login, password and code in Bastion. */
function BastionForm({
  bastionUrl,
  onSignedIn,
}: {
  bastionUrl: string | null
  onSignedIn: (user: User) => void
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ text: string; enroll: boolean } | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await authApi.bastion(username.trim(), password, code.replace(/\s/g, '')))
    } catch (e) {
      const enroll = e instanceof ApiError && e.code === 'totp_not_enrolled'
      setError({ text: (e as Error).message, enroll })
      if (e instanceof ApiError && e.code === 'invalid_totp') setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
      {error && (
        <p
          role="alert"
          className="rounded-[14px] bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {error.text}
          {error.enroll && bastionUrl && (
            <>
              {' '}
              <a href={bastionUrl} target="_blank" rel="noopener noreferrer" className="underline">
                Открыть Bastion
              </a>
            </>
          )}
        </p>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="bastion-username">Логин</Label>
        <Input
          id="bastion-username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="h-12"
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="bastion-password">Пароль</Label>
        <Input
          id="bastion-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-12"
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="bastion-code">Код из приложения</Label>
        <Input
          id="bastion-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9 ]*"
          maxLength={7}
          placeholder="123 456"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="h-12 tracking-[0.2em] tabular-nums"
        />
      </div>
      <Button
        type="submit"
        size="lg"
        className="h-12 text-[15px]"
        disabled={busy || !username.trim() || !password}
      >
        {busy ? <Loader2 className="animate-spin" /> : <LogIn />}
        Войти
      </Button>
    </form>
  )
}

function BotLoginBlock({
  onConfirmed,
  onError,
  secondary = false,
}: {
  onConfirmed: (user?: User) => Promise<void>
  onError: (message: string) => void
  secondary?: boolean
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
        variant={secondary ? 'outline' : 'default'}
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
