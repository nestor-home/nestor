import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { ChatLayout } from "@/features/chat/chat-layout";

export const Route = createFileRoute("/_app/chat")({ component: Chat });

function Chat() {
  return (
    <Guard scope="chat:write">
      <ChatLayout />
    </Guard>
  );
}
