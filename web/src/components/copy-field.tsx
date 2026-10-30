import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { tr } from "@/i18n/runtime";

/** A value to paste elsewhere (a redirect URI, an invitation link), with a copy button. */
export function CopyField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false); // no clipboard (http, permissions): the value stays selectable
    }
  }
  return (
    <div className="flex items-stretch overflow-hidden rounded-md border border-rule-strong bg-paper-sunken">
      <code className="min-w-0 flex-1 truncate px-3 py-2 font-mono text-[0.8rem] text-ink select-all" title={value}>
        {value}
      </code>
      <Button
        variant="ghost"
        className="h-auto rounded-none border-l border-rule-strong px-3"
        onClick={copy}
        aria-label={tr("action-copy-label", { what: label })}
      >
        {copied ? <Check className="text-sage" /> : <Copy />}
        <span className="font-mono text-xs">{copied ? tr("action-copied") : tr("action-copy")}</span>
      </Button>
    </div>
  );
}

/** A small copy action next to something already shown (a raw record). */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="xs"
      aria-label={tr("action-copy-label", { what: label })}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? <Check className="text-sage" /> : <Copy />}
      {copied ? tr("action-copied") : tr("action-copy")}
    </Button>
  );
}
