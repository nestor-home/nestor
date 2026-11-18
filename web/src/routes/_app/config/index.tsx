import { createFileRoute } from "@tanstack/react-router";
import { ConfigOverview } from "@/features/config/overview";

export const Route = createFileRoute("/_app/config/")({ component: ConfigOverview });
