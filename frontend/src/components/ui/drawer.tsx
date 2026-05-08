/**
 * Right-side slide-over panel built on Radix Dialog. We intentionally pass
 * `modal={false}` so opening the drawer does NOT trap focus or block clicks
 * on the underlying table; the user can keep clicking rows to swap the
 * drawer's contents without first closing the panel.
 */

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Drawer({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange} modal={false}>
      {children}
    </DialogPrimitive.Root>
  );
}

export const DrawerTrigger = DialogPrimitive.Trigger;
export const DrawerClose = DialogPrimitive.Close;

export function DrawerContent({
  children,
  className,
  width = "w-full sm:w-[520px]",
}: {
  children: ReactNode;
  className?: string;
  width?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Content
        // Non-modal: don't intercept pointer events outside the panel.
        onInteractOutside={(e) => {
          // Allow clicks anywhere outside the drawer to land on the page,
          // including on the People table to swap the active person.
          e.preventDefault();
        }}
        onPointerDownOutside={(e) => e.preventDefault()}
        className={cn(
          "fixed inset-y-0 right-0 z-40 flex flex-col border-l border-border bg-card shadow-xl outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
          width,
          className,
        )}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DrawerHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("border-b border-border px-6 py-4", className)}>{children}</div>;
}

export function DrawerTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Title className={cn("text-lg font-semibold text-foreground", className)}>
      {children}
    </DialogPrimitive.Title>
  );
}

export function DrawerDescription({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Description className={cn("text-xs text-muted-foreground", className)}>
      {children}
    </DialogPrimitive.Description>
  );
}
