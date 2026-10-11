import { useTheme } from '@/hooks/useTheme'
import { AnimatedThemeToggler } from '@/components/magicui/animated-theme-toggler'

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === 'dark'
  return (
    <AnimatedThemeToggler
      className="theme-toggle"
      duration={350}
      theme={resolvedTheme}
      onThemeChange={setTheme}
      aria-label={dark ? 'Включить светлую тему' : 'Включить темную тему'}
      title={dark ? 'Светлая тема' : 'Темная тема'}
    />
  )
}
