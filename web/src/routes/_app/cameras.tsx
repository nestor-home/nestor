import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { CamerasList } from "@/features/cameras/cameras";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/cameras")({ component: Page });

function Page() {
  const t = useT();
  return (
    <Guard scope="media:read">
      <PageHeader title={t("cam-title")}>{t("cam-lede")}</PageHeader>
      <CamerasList />
    </Guard>
  );
}
