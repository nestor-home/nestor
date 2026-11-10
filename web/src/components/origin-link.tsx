import { Link } from "@tanstack/react-router";
import { MessageSquareText } from "lucide-react";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";

/** Where something was asked (a task, a watch, a reminder): the conversation in the journal, and its channel. */
export function OriginLink({ origin }: { origin: { session: string; channel: string } }) {
  const t = useT();
  return (
    <Link
      to="/journal"
      search={{ session: origin.session }}
      className="inline-flex items-center gap-2 text-ink hover:text-ember"
    >
      <MessageSquareText className="size-4" aria-hidden="true" />
      {t("origin-a-conversation")}
      <span className="inline-flex items-center gap-1 text-[0.85rem] text-ink-muted">
        <KindMark kind={origin.channel} className="size-3" label={false} />
        {kindName(origin.channel)}
      </span>
    </Link>
  );
}
