import { createFileRoute } from "@tanstack/react-router";
import { Conversation } from "@/features/chat/conversation";

export const Route = createFileRoute("/_app/chat/")({ component: NewChat });

function NewChat() {
  return <Conversation chat={null} />;
}
