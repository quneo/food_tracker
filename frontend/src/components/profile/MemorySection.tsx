import { useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, History, ImageIcon, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { memoryApi } from '@/api/endpoints'
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
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { BlockSkeleton, EmptyState, ErrorState } from '@/components/shared/States'
import { FACT_CATEGORIES } from '@/lib/labels'
import { dateTimeLabel, todayIn } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Fact, FactCategory } from '@/types'

export function MemorySection() {
  const client = useQueryClient()
  const [editing, setEditing] = useState<Fact | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Fact | null>(null)
  const facts = useQuery({
    queryKey: keys.memory,
    queryFn: ({ signal }) => memoryApi.list({ signal }),
  })
  const remove = useMutation({
    mutationFn: (id: number) => memoryApi.remove(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.memory })
      toast.success('Факт удален')
    },
    meta: { silent: true },
  })
  const groups = FACT_CATEGORIES.map((category) => ({
    ...category,
    facts: (facts.data ?? []).filter((fact) => fact.category === category.value),
  })).filter((group) => group.facts.length)

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>AI-память</CardTitle>
          <CardDescription>
            Что ассистент помнит о вас между разговорами. Неверное — исправьте или удалите.
          </CardDescription>
          <CardAction>
            <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
              <Plus />
              Добавить
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {facts.isPending ? (
            <BlockSkeleton rows={3} />
          ) : facts.isError ? (
            <ErrorState error={facts.error} retry={() => facts.refetch()} />
          ) : !groups.length ? (
            <EmptyState
              icon={Brain}
              title="Память пуста"
              description="Ассистент запоминает предпочтения, аллергии и привычки из разговора. Можно добавить и самим."
            />
          ) : (
            <div className="flex flex-col gap-5">
              {groups.map((group) => (
                <section key={group.value} aria-labelledby={`facts-${group.value}`}>
                  <h3 id={`facts-${group.value}`} className="section-title mb-1">
                    {group.label}
                  </h3>
                  <ul className="row-list -mx-2">
                    {group.facts.map((fact) => (
                      <li key={fact.id} className="flex items-start gap-2 px-2 py-2">
                        <p className="min-w-0 flex-1 pt-2.5 text-[15px] leading-snug">
                          {fact.text}{' '}
                          <Badge
                            variant="secondary"
                            className={cn(
                              'ml-1 align-middle text-[11px] font-normal',
                              fact.source === 'ai' && 'bg-accent text-accent-foreground',
                            )}
                          >
                            {fact.source === 'ai' ? 'AI' : 'вы'}
                          </Badge>
                        </p>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Действия: ${fact.text}`}
                            >
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setEditing(fact)}>
                              <Pencil />
                              Изменить
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onSelect={() => setDeleting(fact)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 />
                              Удалить
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ChatHistoryCard />

      <ResponsiveSheet
        open={editing !== undefined}
        onOpenChange={(value) => !value && setEditing(undefined)}
        title={editing ? 'Факт' : 'Новый факт'}
      >
        {editing !== undefined && <FactForm fact={editing} onDone={() => setEditing(undefined)} />}
      </ResponsiveSheet>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(value) => !value && setDeleting(null)}
        title="Удалить факт?"
        description={deleting?.text}
        onConfirm={() => remove.mutateAsync(deleting!.id)}
      />
    </div>
  )
}

function FactForm({ fact, onDone }: { fact: Fact | null; onDone: () => void }) {
  const client = useQueryClient()
  const [category, setCategory] = useState<FactCategory>(fact?.category ?? 'preference')
  const [text, setText] = useState(fact?.text ?? '')
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => {
      if (!text.trim()) throw new Error('Напишите текст')
      const data = { category, text: text.trim() }
      return fact ? memoryApi.update(fact.id, data) : memoryApi.create(data)
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.memory })
      toast.success('Сохранено')
      onDone()
    },
    onError: (e) => setError(e.message),
    meta: { silent: true },
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="fact-category">Раздел</Label>
        <Select value={category} onValueChange={(value) => setCategory(value as FactCategory)}>
          <SelectTrigger id="fact-category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FACT_CATEGORIES.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="fact-text">Текст</Label>
        <Textarea
          id="fact-text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          maxLength={500}
          rows={3}
          placeholder="Например, не ест свинину"
          required
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Сохраняем…' : 'Сохранить'}
      </Button>
    </form>
  )
}

function ChatHistoryCard() {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [clearing, setClearing] = useState(false)
  const clear = useMutation({
    mutationFn: () => memoryApi.clearMessages(),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.chat })
      toast.success('История очищена')
    },
    meta: { silent: true },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Диалог с ассистентом</CardTitle>
        <CardDescription>
          Сообщения, которые видел бот. Записи и память при очистке остаются.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setOpen(true)}>
          <History />
          История диалога
        </Button>
        <Button
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => setClearing(true)}
        >
          <Trash2 />
          Очистить историю диалога
        </Button>
      </CardContent>
      <ResponsiveSheet open={open} onOpenChange={setOpen} title="История диалога" wide>
        {open && <ChatHistory />}
      </ResponsiveSheet>
      <ConfirmDialog
        open={clearing}
        onOpenChange={setClearing}
        title="Очистить историю диалога?"
        description="Ассистент забудет переписку. Записи о еде, весе и факты памяти останутся."
        confirmLabel="Очистить"
        onConfirm={() => clear.mutateAsync()}
      />
    </Card>
  )
}

const PAGE = 50

function ChatHistory() {
  const user = useUser()
  const today = todayIn(user.timezone)
  const messages = useInfiniteQuery({
    queryKey: keys.chat,
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam, signal }) => memoryApi.messages(pageParam, PAGE, { signal }),
    getNextPageParam: (last) => (last.length < PAGE ? undefined : last[last.length - 1].id),
  })
  if (messages.isPending) return <BlockSkeleton rows={4} />
  if (messages.isError)
    return <ErrorState error={messages.error} retry={() => messages.refetch()} />
  const list = messages.data.pages.flat()
  if (!list.length)
    return <p className="py-6 text-center text-sm text-muted-foreground">Сообщений нет.</p>
  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2" aria-label="Сообщения, сначала новые">
        {list.map((message) => (
          <li
            key={message.id}
            className={cn(
              'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-snug',
              message.role === 'user'
                ? 'self-end rounded-br-md bg-primary text-primary-foreground'
                : 'self-start rounded-bl-md bg-muted',
            )}
          >
            <span className="sr-only">{message.role === 'user' ? 'Вы: ' : 'Ассистент: '}</span>
            {message.photos > 0 && (
              <span className="mb-1 flex items-center gap-1 text-xs opacity-80">
                <ImageIcon className="size-3.5" aria-hidden="true" />
                фото: {message.photos}
              </span>
            )}
            {message.text && <span className="block whitespace-pre-wrap">{message.text}</span>}
            <span className="mt-1 block text-right text-[11px] opacity-70">
              {dateTimeLabel(message.created_at, today)}
            </span>
          </li>
        ))}
      </ol>
      {messages.hasNextPage && (
        <Button
          variant="outline"
          className="self-center"
          onClick={() => messages.fetchNextPage()}
          disabled={messages.isFetchingNextPage}
        >
          {messages.isFetchingNextPage ? 'Загружаем…' : 'Показать раньше'}
        </Button>
      )}
    </div>
  )
}
