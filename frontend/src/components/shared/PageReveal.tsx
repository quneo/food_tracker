import type { ReactNode } from 'react'
import { BlurFade } from '@/components/magicui/blur-fade'
import { useReducedMotion } from '@/hooks/useMediaQuery'

export function PageReveal({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion()
  return reduced ? (
    <>{children}</>
  ) : (
    <BlurFade duration={0.22} offset={4} blur="2px">
      {children}
    </BlurFade>
  )
}
