import { createFileRoute } from "@tanstack/react-router";
import { SecretsPage } from "@/features/config/secrets-page";

export const Route = createFileRoute("/_app/config/secrets")({ component: SecretsPage });
