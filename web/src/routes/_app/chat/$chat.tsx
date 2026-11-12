import { createFileRoute } from "@tanstack/react-router";
import { Conversation } from "@/features/chat/conversation";

export const Route = createFileRoute("/_app/chat/$chat")({ component: Chat });

function Chat() {
  const { chat } = Route.useParams();
  return <Conversation key={chat} chat={chat} />;
}
