import { createFileRoute } from "@tanstack/react-router";
import { HistoryPage } from "@/features/config/history-page";

export const Route = createFileRoute("/_app/config/history")({ component: HistoryPage });
