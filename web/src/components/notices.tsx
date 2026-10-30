import type { ReactNode } from "react";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";

/** Confirmations after an action ("Compte connecté."), as Sonner toasts, announced politely. */
export function NoticeProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <Toaster />
    </>
  );
}

export function useNotify(): (text: string) => void {
  return notify;
}

function notify(text: string): void {
  toast(text);
}
