import { Link } from "@tanstack/react-router";
import { MessageSquareText } from "lucide-react";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";

/** Where something was asked (a task, an alert): the conversation in the journal, and its channel. */
export function OriginLink({ origin }: { origin: { session: string; channel: string } }) {
  const t = useT();
  return (
    <Link
      to="/journal"
      search={{ session: origin.session }}
      className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5 text-ink hover:text-ember"
    >
      <span className="inline-flex items-center gap-2 whitespace-nowrap">
        <MessageSquareText className="size-4 shrink-0" aria-hidden="true" />
        {t("origin-a-conversation")}
      </span>
      <span className="inline-flex items-center gap-1 text-meta whitespace-nowrap text-ink-muted">
        <KindMark kind={origin.channel} className="size-3" label={false} />
        {kindName(origin.channel)}
      </span>
    </Link>
  );
}
