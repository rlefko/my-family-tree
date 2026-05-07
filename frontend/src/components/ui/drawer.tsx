/**
 * Right-side slide-over panel built on Radix Dialog. Used by the People page
 * to surface a person's full detail without leaving the table.
 */

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Drawer = DialogPrimitive.Root;
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
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-zinc-900/30 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex flex-col border-l border-zinc-200 bg-white shadow-xl outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
          width,
          className,
        )}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 rounded-md p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DrawerHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("border-b border-zinc-200 px-6 py-4", className)}>
      {children}
    </div>
  );
}

export function DrawerTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Title className={cn("text-lg font-semibold text-zinc-900", className)}>
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
    <DialogPrimitive.Description className={cn("text-xs text-zinc-500", className)}>
      {children}
    </DialogPrimitive.Description>
  );
}
