/**
 * One draft of the configuration file for the whole Configuration area: every page edits it, a
 * debounced preview checks it (problems located at their fields, the changes), and one save
 * writes it. Nothing is applied before a person restarts the instance.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type ConfigDiff,
  type ConfigDocument,
  type ConfigProblem,
  type ConfigSchema,
  type ConfigState,
  configQuery,
  configSchemaQuery,
  keys,
} from "@/api";
import { Failure, Loading } from "@/components/states";
import { type Path, setAt } from "./schema";

const PREVIEW_DELAY_MS = 400;

export interface ConfigEditor {
  schema: ConfigSchema;
  state: ConfigState;
  /** What the file holds now (masked), and the edited document. */
  base: ConfigDocument;
  draft: ConfigDocument;
  dirty: boolean;
  set: (path: Path, value: unknown) => void;
  replace: (next: ConfigDocument) => void;
  discard: () => void;
  /** The last preview of the draft: located problems and the changes saving would make. */
  problems: ConfigProblem[];
  diff: ConfigDiff | null;
  checking: boolean;
  save: () => Promise<boolean>;
  saving: boolean;
  saveError: unknown;
}

const Context = createContext<ConfigEditor | null>(null);

export function useConfigEditor(): ConfigEditor {
  const editor = useContext(Context);
  if (!editor) throw new Error("useConfigEditor outside ConfigEditorProvider");
  return editor;
}

function useDebounced<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export function ConfigEditorProvider({ children }: { children: ReactNode }) {
  const schema = useQuery(configSchemaQuery);
  const state = useQuery(configQuery);
  if (schema.isPending || state.isPending) return <Loading lines={5} />;
  if (schema.isError) return <Failure error={schema.error} retry={() => void schema.refetch()} />;
  if (state.isError) return <Failure error={state.error} retry={() => void state.refetch()} />;
  return (
    <Editing schema={schema.data} state={state.data}>
      {children}
    </Editing>
  );
}

function Editing({ schema, state, children }: { schema: ConfigSchema; state: ConfigState; children: ReactNode }) {
  const queryClient = useQueryClient();
  const base = state.document;
  const [draft, setDraft] = useState<ConfigDocument>(base);
  const [refused, setRefused] = useState<ConfigProblem[] | null>(null);

  // a fresh file (after a save, a restore, a restart) becomes the new starting point
  useEffect(() => {
    setDraft(base);
    setRefused(null);
  }, [base]);

  const serialized = useMemo(() => JSON.stringify(draft), [draft]);
  const dirty = serialized !== JSON.stringify(base);
  const settled = useDebounced(serialized, PREVIEW_DELAY_MS);
  const preview = useQuery({
    queryKey: [...keys.config, "preview", settled] as const,
    queryFn: ({ signal }) => api.previewConfig(JSON.parse(settled) as ConfigDocument, signal),
    enabled: dirty && settled !== JSON.stringify(base),
    placeholderData: keepPreviousData,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

  const set = useCallback((path: Path, value: unknown) => {
    setRefused(null);
    setDraft((current) => setAt(current, path, value));
  }, []);
  const replace = useCallback((next: ConfigDocument) => {
    setRefused(null);
    setDraft(next);
  }, []);
  const discard = useCallback(() => {
    setRefused(null);
    setDraft(base);
  }, [base]);

  const write = useMutation({
    mutationFn: () => api.writeConfig(draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.config });
      void queryClient.invalidateQueries({ queryKey: keys.me });
      void queryClient.invalidateQueries({ queryKey: keys.system });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.problems.length) setRefused(error.problems);
    },
  });

  const current = dirty && preview.data && !preview.isPlaceholderData ? preview.data : null;
  const problems = refused ?? (dirty ? (preview.data?.problems ?? []) : []);
  const editor: ConfigEditor = {
    schema,
    state,
    base,
    draft,
    dirty,
    set,
    replace,
    discard,
    problems,
    diff: dirty ? (current?.diff ?? preview.data?.diff ?? null) : null,
    checking: dirty && (settled !== serialized || preview.isFetching),
    save: async () => {
      try {
        await write.mutateAsync();
        return true;
      } catch {
        return false;
      }
    },
    saving: write.isPending,
    saveError: write.error,
  };
  return <Context.Provider value={editor}>{children}</Context.Provider>;
}

/** The number of changes a diff holds. */
export const changeCount = (diff: ConfigDiff | null): number =>
  diff ? diff.added.length + diff.removed.length + diff.changed.length : 0;
