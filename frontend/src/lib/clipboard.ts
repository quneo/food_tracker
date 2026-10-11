/**
 * Copies text. The Clipboard API exists only in secure contexts (https, localhost); at
 * home the site is opened as http://<LAN IP>, so fall back to a hidden textarea and
 * execCommand('copy'), which browsers still allow there on a click.
 */
export async function copyText(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      /* Denied: try the old way below. */
    }
  }
  const active = document.activeElement as HTMLElement | null
  const selection = document.getSelection()
  const ranges = selection
    ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i))
    : []
  const area = document.createElement('textarea')
  area.value = text
  area.readOnly = true
  area.setAttribute('aria-hidden', 'true')
  Object.assign(area.style, { position: 'fixed', top: '0', left: '-9999px', opacity: '0' })
  document.body.appendChild(area)
  area.focus({ preventScroll: true })
  area.select()
  area.setSelectionRange(0, text.length)
  let copied = false
  try {
    copied = document.execCommand('copy')
  } catch {
    copied = false
  }
  area.remove()
  if (selection) {
    selection.removeAllRanges()
    ranges.forEach((range) => selection.addRange(range))
  }
  active?.focus({ preventScroll: true })
  return copied
}
