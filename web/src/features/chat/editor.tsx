/**
 * The composer's text, a TipTap editor: plain paragraphs, and executors named with `@` as tags that are one piece
 * (the executor's mark and name), deleted at once. Typing `@` offers the executors plugged in; the arrows choose,
 * Enter or Tab writes the tag, Escape closes. Enter sends, Shift+Enter goes to the line. What is sent is the text,
 * each tag written back as `@name`.
 */
import { useQuery } from "@tanstack/react-query";
import { Extension, type JSONContent } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Mention from "@tiptap/extension-mention";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { Placeholder } from "@tiptap/extensions";
import {
  EditorContent,
  type NodeViewProps,
  NodeViewWrapper,
  ReactNodeViewRenderer,
  useEditor,
  useEditorState,
} from "@tiptap/react";
import type { SuggestionKeyDownProps, SuggestionProps } from "@tiptap/suggestion";
import { type Ref, useImperativeHandle, useRef, useState } from "react";
import { type Mention as Executor, mentionsQuery } from "@/api";
import { MentionList, MentionTag, NAMED } from "./mentions";

export interface EditorHandle {
  text: () => string;
  clear: () => void;
  focus: () => void;
  mention: () => void; // writes `@`, which opens the list
}

interface Offer {
  items: Executor[];
  command: (item: { id: string }) => void;
}

/** A saved draft as the editor's document: its known `@name`s back as tags. */
function documentOf(text: string, known: Set<string>): JSONContent {
  return {
    type: "doc",
    content: text.split("\n").map((line) => ({
      type: "paragraph",
      content: line
        ? line
            .split(NAMED)
            .filter(Boolean)
            .map((part) =>
              known.has(part.slice(1)) && part.startsWith("@")
                ? { type: "mention", attrs: { id: part.slice(1) } }
                : { type: "text", text: part },
            )
        : undefined,
    })),
  };
}

function Tag({ node }: NodeViewProps) {
  const { data: mentions = [] } = useQuery(mentionsQuery);
  const id = String(node.attrs.id);
  const mention = mentions.find((m) => m.name === id) ?? { name: id, description: "", brand: null };
  return (
    <NodeViewWrapper as="span" className="inline">
      <MentionTag mention={mention} />
    </NodeViewWrapper>
  );
}

export function ChatEditor({
  ref,
  initial,
  placeholder,
  onChange,
  onSubmit,
  onFiles,
  autoFocus,
}: {
  ref?: Ref<EditorHandle>;
  initial: string;
  placeholder: string;
  onChange: (text: string) => void;
  onSubmit: () => void;
  onFiles: (files: File[]) => void;
  autoFocus?: boolean;
}) {
  const { data: mentions = [] } = useQuery(mentionsQuery);
  const executors = useRef(mentions);
  executors.current = mentions;
  const submit = useRef(onSubmit);
  submit.current = onSubmit;
  const [offer, setOffer] = useState<Offer | null>(null);
  const [active, setActive] = useState(0);
  const picking = useRef<{ offer: Offer | null; active: number }>({ offer: null, active: 0 });
  picking.current = { offer, active };

  const editor = useEditor({
    extensions: [
      Document,
      Paragraph,
      Text,
      HardBreak,
      Placeholder.configure({ placeholder }),
      Mention.extend({ addNodeView: () => ReactNodeViewRenderer(Tag, { as: "span" }) }).configure({
        renderText: ({ node }) => `@${node.attrs.id}`,
        deleteTriggerWithBackspace: true,
        suggestion: {
          items: ({ query }) =>
            executors.current.filter((m) => m.name.toLocaleLowerCase().startsWith(query.toLocaleLowerCase())),
          render: () => ({
            onStart: (props: SuggestionProps<Executor>) => {
              setActive(0);
              setOffer({ items: props.items, command: props.command });
            },
            onUpdate: (props: SuggestionProps<Executor>) => {
              setActive(0);
              setOffer({ items: props.items, command: props.command });
            },
            onKeyDown: ({ event }: SuggestionKeyDownProps) => choose(event),
            onExit: () => setOffer(null),
          }),
        },
      }),
      // Enter sends, unless an executor is being chosen: the list's own keys take it then
      Extension.create({
        name: "send",
        priority: 1000,
        addKeyboardShortcuts: () => ({
          // biome-ignore lint/correctness/noComponentHookFactories: a key name, not a component
          Enter: () => {
            if (picking.current.offer?.items.length) return false;
            submit.current();
            return true;
          },
        }),
      }),
    ],
    content: documentOf(initial, new Set(mentions.map((m) => m.name))),
    autofocus: autoFocus ? "end" : false,
    editorProps: {
      attributes: {
        "aria-label": placeholder,
        "aria-multiline": "true",
        role: "textbox",
        class:
          "chat-editor max-h-60 min-h-12 overflow-y-auto px-4 pt-3.5 pb-1 text-[0.95rem] leading-relaxed text-ink outline-none [overflow-wrap:anywhere]",
      },
      handlePaste: (_view, event) => {
        const files = [...(event.clipboardData?.files ?? [])];
        if (!files.length) return false;
        onFiles(files);
        return true;
      },
    },
    onUpdate: ({ editor }) => onChange(editor.getText({ blockSeparator: "\n" })),
  });

  /** The list's keys while it is open; true when the key was its. */
  function choose(event: KeyboardEvent): boolean {
    const { offer: open, active: current } = picking.current;
    if (!open?.items.length) return false;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + open.items.length) % open.items.length);
      return true;
    }
    if ((event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
      const item = open.items[current];
      if (item) open.command({ id: item.name });
      return true;
    }
    return event.key === "Escape";
  }

  // re-render on every change of the document: the placeholder and the list follow it
  useEditorState({ editor, selector: ({ editor }) => editor?.state.doc.content.size });

  useImperativeHandle(ref, () => ({
    text: () => editor?.getText({ blockSeparator: "\n" }) ?? "",
    clear: () => {
      editor?.commands.clearContent(true);
    },
    focus: () => {
      editor?.commands.focus("end");
    },
    mention: () => {
      if (!editor) return;
      const { from } = editor.state.selection;
      const before = editor.state.doc.textBetween(Math.max(0, from - 1), from, "\n", " ");
      editor
        .chain()
        .focus()
        .insertContent(before && !/\s/.test(before) ? " @" : "@")
        .run();
    },
  }));

  return (
    <>
      {offer?.items.length ? (
        <MentionList
          options={offer.items}
          active={Math.min(active, offer.items.length - 1)}
          onChoose={(item) => offer.command({ id: item.name })}
        />
      ) : null}
      <EditorContent editor={editor} />
    </>
  );
}
