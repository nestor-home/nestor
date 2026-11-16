import type { Account, Role } from "@/api";

/** Whether the account is an owner's (an owner may use everything, whatever a list says). */
export const isOwner = (account: { role: Role } | null | undefined): boolean => account?.role === "owner";

/**
 * Whether changing this account could leave the household without an active owner. The server
 * refuses it anyway; the screen says why before anyone tries.
 */
export function isLastOwner(account: Account, accounts: readonly Account[]): boolean {
  if (!isOwner(account) || account.disabled) return false;
  return accounts.filter((a) => isOwner(a) && !a.disabled).length <= 1;
}
