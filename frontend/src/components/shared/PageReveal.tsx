import type { ReactNode } from 'react'
import { motion } from 'motion/react'

/**
 * A quiet fade between pages. Opacity only, nothing that stays applied afterwards: a
 * lingering filter or transform on an ancestor would stop the frosted sheets from
 * blurring the wallpaper behind them. Reduced motion is honored by MotionConfig.
 */
export function PageReveal({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}
