/**
 * One chat: its messages from the journal, the answer being written over them, and the composer. A new chat (no id
 * yet) greets and centres the composer; its first message gives it an id and opens it. The chat follows its live
 * entries (a tool called, a result coming back by itself) and, opened while an answer is written, follows it again.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowDown, MessagesSquare, SquarePen, Upload } from "lucide-react";
import { type DragEvent, memo, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import {
  api,
  type ChatMessage,
  type ChatMessageIn,
  chatQuery,
  chatsQuery,
  keys,
  mentionsQuery,
  messageOf,
} from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { SideSheet } from "@/components/overlay-form";
import { Failure, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useLiveItems } from "@/features/shell/live";
import { useT } from "@/i18n";
import { useMe } from "@/lib/session";
import { cn, randomId } from "@/lib/utils";
import { ChatList, titleOf } from "./chat-layout";
import { Composer, type ComposerHandle } from "./composer";
import { dismiss, type LiveAnswer, rejoin, send, useLiveAnswer } from "./live";
import { Answer, AnswerActions, ARRIVES, Fallback, Files, Note, PersonMessage, ToolCall } from "./message";

export function Conversation({ chat }: { chat: string | null }) {
  const t = useT();
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const thread = useQuery({ ...chatQuery(chat ?? ""), enabled: chat !== null });
  const live = useLiveAnswer(chat);
  const composer = useRef<ComposerHandle>(null);
  const [dragging, setDragging] = useState(false);
  const messages = thread.data?.messages ?? [];

  const settled = (id: string) => async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.chat(id) }),
      queryClient.invalidateQueries({ queryKey: keys.chats, exact: true }),
    ]);
  };

  // opened while an answer is being written (another tab, a reload): follow it from its start
  const answering = thread.data?.answering;
  // biome-ignore lint/correctness/useExhaustiveDependencies: once per answer, with the messages it found
  useEffect(() => {
    if (chat && answering) void rejoin(chat, openedAt(messages), settled(chat)).catch(() => undefined);
  }, [chat, answering]);

  useLiveItems((item) => {
    if (chat && thread.data && item.links.session === thread.data.session) {
      void queryClient.invalidateQueries({ queryKey: keys.chat(chat) });
    }
  });

  const onSend = async (body: ChatMessageIn): Promise<boolean> => {
    const id = chat ?? randomId();
    if (live?.state === "failed") dismiss(id);
    try {
      const started = send(id, body, messages.at(-1)?.position ?? 0, settled(id));
      if (!chat) void navigate({ to: "/chat/$chat", params: { chat: id } });
      await started;
      return true;
    } catch (error) {
      toast.error(messageOf(error));
      return false;
    }
  };

  const onStop = () => {
    if (chat) void api.stopChat(chat).catch((error) => toast.error(messageOf(error)));
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) composer.current?.add(event.dataTransfer.files);
  };

  const fresh = chat === null || (thread.isSuccess && !messages.length && !live);
  const busy = live !== null && (live.state === "waiting" || live.state === "writing");

  return (
    <section
      className="relative flex min-h-0 flex-1 flex-col"
      aria-label={t("chat-title")}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <Header chat={chat} />
      {chat !== null && thread.isPending ? (
        <div className="mx-auto w-full max-w-3xl px-4 pt-10">
          <Loading lines={4} />
        </div>
      ) : chat !== null && thread.error ? (
        <div className="mx-auto w-full max-w-3xl px-4 pt-10">
          <Failure error={thread.error} retry={thread.refetch} />
        </div>
      ) : (
        <div className={cn("flex min-h-0 flex-1 flex-col", fresh && "justify-center gap-8 pb-[12vh]")}>
          {fresh ? (
            <div className={cn("flex flex-col items-center gap-4 px-4 text-center", ARRIVES, "duration-500")}>
              <AgentFigure state="idle" size="lg" live />
              <p className="display-2 text-ink">{t("chat-greeting", { assistant: me.assistant })}</p>
            </div>
          ) : (
            <StickToBottom className="relative min-h-0 flex-1 overflow-hidden" resize="smooth" initial="instant">
              <StickToBottom.Content className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 pt-6 pb-10">
                <Thread messages={messages} live={live} assistant={me.assistant} />
              </StickToBottom.Content>
              <ScrollDown />
            </StickToBottom>
          )}
          <div className="mx-auto w-full max-w-3xl px-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
            <Composer
              ref={composer}
              draftKey={chat ?? "new"}
              assistant={me.assistant}
              answering={busy}
              onSend={onSend}
              onStop={onStop}
            />
          </div>
        </div>
      )}
      {dragging ? (
        <div className="pointer-events-none absolute inset-2 z-20 grid animate-in place-items-center rounded-2xl border-2 border-dashed border-ember bg-paper/90 duration-150 fade-in-0 motion-reduce:animate-none">
          <p className="flex items-center gap-2 text-ink">
            <Upload className="size-5 text-ember" aria-hidden="true" />
            {t("chat-drop")}
          </p>
        </div>
      ) : null}
    </section>
  );
}

/** Where the turn being answered opened: its person's message or Nestor's note, the last one logged. */
function openedAt(messages: ChatMessage[]): number {
  const opening = messages.findLast((m) => m.role === "person" || m.role === "note");
  return opening?.position ?? 0;
}

function Thread({
  messages,
  live,
  assistant,
}: {
  messages: ChatMessage[];
  live: LiveAnswer | null;
  assistant: string;
}) {
  const t = useT();
  const { data: mentions = [] } = useQuery(mentionsQuery); // what the message sent can name, before it is logged
  // what the journal has not logged yet: the message sent, then the answer's messages beyond those it logged; what
  // came in meanwhile (Nestor coming back with a task's result) comes before the message sent, never in the answer
  const since = live ? messages.filter((m) => m.position > live.after) : [];
  const own = live?.sent ? since.findIndex((m) => m.role === "person") : -1;
  const pending = live?.sent && own < 0 ? live.sent : null;
  const answered = live?.sent ? (own < 0 ? [] : since.slice(own + 1)) : since;
  const written = live ? live.messages.slice(answered.filter((m) => m.role === "assistant").length) : [];
  const last = messages.at(-1);
  // what came in while the chat was open (a tool called, Nestor coming back) arrives; what was there stays put
  const opened = useRef(last?.position ?? 0);
  const arrives = useCallback(
    (message: ChatMessage) => message.position > opened.current && message.role !== "assistant",
    [],
  );
  const waiting = live && (live.state === "waiting" || (live.state === "writing" && !live.writing));

  return (
    <>
      <History messages={messages} assistant={assistant} arrives={arrives} />
      {pending ? (
        <PersonMessage
          text={pending.text ?? ""}
          mentions={mentions}
          pending
          files={pending.files?.length ? <SentFiles count={pending.files.length} /> : null}
        />
      ) : null}
      {written.map((text, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: the answer's messages only grow at the end
        <AnswerBlock key={i} arrives>
          <Answer text={text} streaming={live?.writing && i === written.length - 1} />
        </AnswerBlock>
      ))}
      {waiting ? (
        last?.role === "tool" && last.tool?.state === "running" ? (
          <Thinking state="working" text={t("chat-working", { assistant, tool: last.tool.name })} />
        ) : (
          <Thinking state="thinking" text={t("chat-thinking", { assistant })} />
        )
      ) : null}
      {live?.state === "failed" ? <Fallback text={live.error ?? t("chat-failed")} /> : null}
    </>
  );
}

type Group = { kind: "tools"; key: string; calls: ChatMessage[] } | { kind: "one"; key: string; message: ChatMessage };

/** Tool calls that follow each other stack together; every other message stands alone. */
function groups(messages: ChatMessage[]): Group[] {
  const found: Group[] = [];
  for (const message of messages) {
    const previous = found.at(-1);
    if (message.role !== "tool") found.push({ kind: "one", key: message.id, message });
    else if (previous?.kind === "tools") previous.calls.push(message);
    else found.push({ kind: "tools", key: message.id, calls: [message] });
  }
  return found;
}

/** What the journal holds of the chat; it renders again only when the journal does, not at each streamed word. */
const History = memo(function History({
  messages,
  assistant,
  arrives,
}: {
  messages: ChatMessage[];
  assistant: string;
  arrives: (message: ChatMessage) => boolean;
}) {
  return groups(messages).map((group) =>
    group.kind === "tools" ? (
      <div key={group.key} className="grid gap-1.5">
        {group.calls.map((m) => (
          <div key={m.id} className={cn(arrives(m) && ARRIVES)}>
            {m.tool ? <ToolCall tool={m.tool} /> : null}
          </div>
        ))}
      </div>
    ) : (
      <div
        key={group.key}
        className={cn("min-w-0", group.message.role === "note" && arrives(group.message) && ARRIVES)}
      >
        <Message message={group.message} assistant={assistant} />
      </div>
    ),
  );
});

function Message({ message, assistant }: { message: ChatMessage; assistant: string }) {
  switch (message.role) {
    case "person":
      return (
        <PersonMessage
          text={message.text}
          mentions={message.mentions}
          files={<Files files={message.files} align="end" />}
        />
      );
    case "assistant":
      return (
        <AnswerBlock>
          <Answer text={message.text} />
          <Files files={message.files} />
          <AnswerActions text={message.text} interrupted={message.interrupted} />
        </AnswerBlock>
      );
    case "note":
      return <Note text={message.text} assistant={assistant} />;
    case "fallback":
      return <Fallback text={message.text} />;
    default:
      return null;
  }
}

function AnswerBlock({ children, arrives }: { children: ReactNode; arrives?: boolean }) {
  return <div className={cn("group/answer grid min-w-0 gap-2", arrives && ARRIVES)}>{children}</div>;
}

function SentFiles({ count }: { count: number }) {
  const t = useT();
  return <p className="text-[0.8rem] text-ink-muted">{t("chat-sending-files", { count })}</p>;
}

function Thinking({ state, text }: { state: "thinking" | "working"; text: string }) {
  return (
    <div className={cn("flex items-center gap-2.5 text-[0.9rem] text-ink-muted", ARRIVES)} role="status">
      <AgentFigure state={state} size="sm" live />
      <span className="chat-shimmer">{text}</span>
    </div>
  );
}

function ScrollDown() {
  const t = useT();
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();
  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => void scrollToBottom()}
      aria-label={t("chat-scroll-down")}
      className="absolute bottom-4 left-1/2 -translate-x-1/2 animate-in rounded-full shadow-sm duration-200 fade-in-0 zoom-in-90 motion-reduce:animate-none"
    >
      <ArrowDown />
    </Button>
  );
}

/** The chat's name, and below `lg` the list of chats and a new one at hand. */
function Header({ chat }: { chat: string | null }) {
  const t = useT();
  const chats = useQuery(chatsQuery);
  const [open, setOpen] = useState(false);
  const found = chats.data?.chats.find((c) => c.id === chat);
  const title = found ? titleOf(found, t) : t("chat-new");
  return (
    <header className="flex h-12 shrink-0 items-center gap-1 border-b border-rule px-2 lg:px-4">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={() => setOpen(true)}
        aria-label={t("chat-list")}
      >
        <MessagesSquare />
      </Button>
      <h1 className="min-w-0 flex-1 truncate text-[0.95rem] text-ink">{title}</h1>
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        aria-label={t("chat-new")}
        nativeButton={false}
        render={<Link to="/chat" />}
      >
        <SquarePen />
      </Button>
      <SideSheet open={open} onOpenChange={setOpen}>
        <ChatList onNavigate={() => setOpen(false)} inSheet />
      </SideSheet>
    </header>
  );
}
