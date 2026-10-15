import type { ReactNode } from 'react'
import { useDesktop } from '@/hooks/useMediaQuery'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import { cn } from '@/lib/utils'

/** A bottom drawer on phones, a dialog on wider screens. */
export function ResponsiveSheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  wide?: boolean
}) {
  const desktop = useDesktop()
  const describedBy = description ? {} : { 'aria-describedby': undefined }
  if (desktop)
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className={cn('editor-dialog', wide ? 'sm:max-w-[680px]' : 'sm:max-w-[480px]')}
          {...describedBy}
        >
          <DialogHeader className="pr-10">
            <DialogTitle className="text-lg">{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          {children}
        </DialogContent>
      </Dialog>
    )
  return (
    <Drawer open={open} onOpenChange={onOpenChange} repositionInputs={false}>
      <DrawerContent {...describedBy}>
        <DrawerHeader>
          <DrawerTitle className="text-lg">{title}</DrawerTitle>
          {description && <DrawerDescription>{description}</DrawerDescription>}
        </DrawerHeader>
        <div className="editor-body">{children}</div>
      </DrawerContent>
    </Drawer>
  )
}
