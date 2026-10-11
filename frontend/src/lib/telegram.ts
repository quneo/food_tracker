/** What the page was opened with: Mini App launch data and an invite code. */
export interface Launch {
  initData: string | null
  telegramId: number | null
  invite: string | null
}

let launch: Launch | null = null

/**
 * Read once at startup. Telegram passes Mini App data in the URL hash
 * (#tgWebAppData=...&tgWebAppVersion=...); it is removed from the address bar right away
 * so the signed data does not stay in history or get shared with a link.
 */
export function takeLaunch(): Launch {
  if (launch) return launch
  let initData: string | null = null
  let telegramId: number | null = null
  try {
    const hash = window.location.hash.slice(1)
    if (hash.includes('tgWebAppData')) {
      initData = new URLSearchParams(hash).get('tgWebAppData')
      window.history.replaceState(
        window.history.state,
        '',
        window.location.pathname + window.location.search,
      )
    }
    if (initData) {
      const user = new URLSearchParams(initData).get('user')
      telegramId = user ? Number(JSON.parse(user).id) || null : null
    }
  } catch {
    /* Malformed launch data: the person signs in another way. */
  }
  const invite = new URLSearchParams(window.location.search).get('invite')
  launch = { initData, telegramId, invite: invite ? invite.slice(0, 64) : null }
  return launch
}

export const botLink = (username: string) => `https://t.me/${username}`
