import { useMemo, useState } from 'react'
import { Check, ChevronDown, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ResponsiveSheet } from '@/components/shared/ResponsiveSheet'
import { cn } from '@/lib/utils'

function zones(): string[] {
  try {
    const list = (
      Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    ).supportedValuesOf?.('timeZone')
    if (list?.length) return list.includes('UTC') ? list : ['UTC', ...list]
  } catch {
    /* Older browsers: fall back to a short list below. */
  }
  return ['UTC', 'Europe/Moscow', 'Asia/Krasnoyarsk', 'Asia/Novosibirsk', 'Asia/Yekaterinburg']
}

/** Offset of a zone right now, like "UTC+7". */
function offset(zone: string) {
  try {
    const part = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'shortOffset' })
      .formatToParts(new Date())
      .find((item) => item.type === 'timeZoneName')
    return part?.value.replace('GMT', 'UTC') ?? ''
  } catch {
    return ''
  }
}

/** A searchable list of IANA time zones. */
export function TimezonePicker({
  id,
  value,
  onChange,
}: {
  id?: string
  value: string
  onChange: (zone: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const all = useMemo(zones, [])
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone
  const needle = search.trim().toLowerCase().replace(/\s+/g, '_')
  const found = (needle ? all.filter((zone) => zone.toLowerCase().includes(needle)) : all).slice(
    0,
    150,
  )

  function pick(zone: string) {
    onChange(zone)
    setOpen(false)
    setSearch('')
  }

  return (
    <>
      <Button
        id={id}
        type="button"
        variant="outline"
        className="w-full justify-between bg-card font-normal"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span className="truncate">
          {value} <span className="text-muted-foreground">{offset(value)}</span>
        </span>
        <ChevronDown className="text-muted-foreground" />
      </Button>
      <ResponsiveSheet open={open} onOpenChange={setOpen} title="Часовой пояс">
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Город, например Krasnoyarsk"
              aria-label="Поиск часового пояса"
              className="pl-9"
              autoFocus
            />
          </div>
          {browser && browser !== value && !needle && (
            <Button
              type="button"
              variant="secondary"
              className="justify-start"
              onClick={() => pick(browser)}
            >
              Как на этом устройстве: {browser}
            </Button>
          )}
          <ul
            className="-mx-1 max-h-[50dvh] overflow-y-auto"
            role="listbox"
            aria-label="Часовые пояса"
          >
            {found.map((zone) => (
              <li key={zone} role="option" aria-selected={zone === value}>
                <button
                  type="button"
                  onClick={() => pick(zone)}
                  className={cn(
                    'flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-3 text-left text-sm hover:bg-muted',
                    zone === value && 'bg-accent text-accent-foreground',
                  )}
                >
                  <span className="truncate">{zone.replace(/_/g, ' ')}</span>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                    {offset(zone)}
                    {zone === value && <Check className="size-4 text-accent-foreground" />}
                  </span>
                </button>
              </li>
            ))}
            {!found.length && (
              <li className="px-3 py-4 text-sm text-muted-foreground">Ничего не найдено</li>
            )}
          </ul>
        </div>
      </ResponsiveSheet>
    </>
  )
}
