import { createFileRoute } from "@tanstack/react-router";
import { ActivityView } from "@/features/activity/activity-view";

export const Route = createFileRoute("/_app/activity")({ component: ActivityView });
