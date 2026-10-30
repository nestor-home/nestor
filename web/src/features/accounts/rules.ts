import type { Account } from "@/api";

/**
 * Whether changing this account could leave the household without an active owner. The server
 * refuses it anyway; the screen says why before anyone tries.
 */
export function isLastOwner(account: Account, accounts: readonly Account[]): boolean {
  if (account.role !== "owner" || account.disabled) return false;
  return accounts.filter((a) => a.role === "owner" && !a.disabled).length <= 1;
}
