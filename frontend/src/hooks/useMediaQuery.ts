import { useEffect, useState } from 'react'

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    media.addEventListener('change', update)
    update()
    return () => media.removeEventListener('change', update)
  }, [query])
  return matches
}

export const useDesktop = () => useMediaQuery('(min-width: 768px)')
export const useReducedMotion = () => useMediaQuery('(prefers-reduced-motion: reduce)')
