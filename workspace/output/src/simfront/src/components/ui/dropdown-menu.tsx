import { Menu } from '@base-ui/react/menu'

import { cn } from '@/lib/utils'

const DropdownMenu = Menu.Root

// Wrap Menu.Trigger to accept (and discard) the `asChild` prop that
// callers from other US pass (shadcn pattern). base-ui does not use asChild.
function DropdownMenuTrigger({
  asChild: _asChild,
  ...props
}: React.ComponentPropsWithoutRef<typeof Menu.Trigger> & { asChild?: boolean }) {
  return <Menu.Trigger {...props} />
}

function DropdownMenuContent({
  className,
  sideOffset = 4,
  // Accept and discard `align` — base-ui uses Positioner alignment instead
  align: _align,
  ...props
}: React.ComponentPropsWithoutRef<typeof Menu.Popup> & {
  sideOffset?: number
  align?: string
}) {
  return (
    <Menu.Portal>
      <Menu.Positioner sideOffset={sideOffset}>
        <Menu.Popup
          className={cn(
            'z-50 min-w-[8rem] overflow-hidden rounded-lg border bg-popover p-1 text-popover-foreground shadow-md',
            'data-[starting-style]:animate-in data-[starting-style]:fade-in-0 data-[starting-style]:zoom-in-95',
            'data-[ending-style]:animate-out data-[ending-style]:fade-out-0 data-[ending-style]:zoom-out-95',
            className
          )}
          {...props}
        />
      </Menu.Positioner>
    </Menu.Portal>
  )
}

function DropdownMenuItem({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof Menu.Item>) {
  return (
    <Menu.Item
      className={cn(
        'relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors',
        'hover:bg-accent hover:text-accent-foreground',
        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        className
      )}
      {...props}
    />
  )
}

function DropdownMenuSeparator({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="separator"
      className={cn('-mx-1 my-1 h-px bg-muted', className)}
      {...props}
    />
  )
}

function DropdownMenuLabel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('px-2 py-1.5 text-sm font-semibold', className)}
      {...props}
    />
  )
}

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
}
