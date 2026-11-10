import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { MessagesView } from "@/features/messages/messages";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/messages")({ component: Page });

function Page() {
  const t = useT();
  return (
    <Guard scope="messages:read">
      <PageHeader title={t("message-title")}>{t("message-lede")}</PageHeader>
      <MessagesView />
    </Guard>
  );
}
