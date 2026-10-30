/**
 * The centrepiece of the home: the agent at the centre, the house it perceives on its left (rooms,
 * their devices, who is there), what it reaches on its right (channels, running tasks, watches,
 * connections). Nodes are links; the lines and the rings are drawn underneath. Live events make
 * the agent ripple and their node glow. Below `md` the same nodes stack into a vertical map.
 */
import { Link, type LinkProps } from "@tanstack/react-router";
import { Cable, House, MessagesSquare, Radar, Workflow } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import type { Agent, Person } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { useT } from "@/i18n";
import { BrandMark, brandOf, KindMark } from "@/lib/brands";
import { cn } from "@/lib/utils";
import { type AgentState, arc, type Reach, type RoomNode } from "./mind";

const STATE_TONE: Record<AgentState, string> = {
  listening: "bg-sage",
  thinking: "bg-amber",
  speaking: "bg-ember",
  laughing: "bg-ember",
  working: "bg-kind-task",
  concerned: "bg-brick",
  sleeping: "bg-ink-faint",
  idle: "bg-ink-faint",
};

export interface MindProps {
  agent: Agent;
  state: AgentState;
  calm: boolean; // nothing needs a person
  rooms: RoomNode[];
  away: Person[];
  reach: Reach | null;
  /** What it says right now, in its own words. */
  line: string;
  /** The node its attention is on (the latest event's), to look toward. */
  focus: string | null;
  /** Node key → when it last received an event (ms), to glow. */
  pulses: Record<string, number>;
  now: number;
}

interface Placed {
  key: string;
  x: number;
  y: number;
  node: ReactNode;
}

/** How long a node glows after an event. */
const GLOW_MS = 3_000;

export function AgentMind(props: MindProps) {
  const t = useT();
  const left = leftNodes(props);
  const right = rightNodes(props);
  const placedLeft = arc(left.length, -1).map((p, i) => ({ ...p, ...(left[i] as Omit<Placed, "x" | "y">) }));
  const placedRight = arc(right.length, 1).map((p, i) => ({ ...p, ...(right[i] as Omit<Placed, "x" | "y">) }));
  const placed: Placed[] = [...placedLeft, ...placedRight];
  const glowing = (key: string) => props.now - (props.pulses[key] ?? 0) < GLOW_MS;
  const target = placed.find((p) => p.key === props.focus);
  const lookAt = target ? { x: (target.x - 50) / 40, y: (target.y - 50) / 45 } : undefined;
  return (
    <section
      aria-labelledby="mind-title"
      className="corner-marks relative min-w-0 rounded-md border border-rule bg-paper-raised"
    >
      <h2 id="mind-title" className="sr-only">
        {t("home-mind-title", { agent: props.agent.name })}
      </h2>
      {/* the map, from md up */}
      <div className="relative hidden h-[30rem] md:block lg:h-[32rem]">
        <svg
          aria-hidden="true"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 size-full"
        >
          {[14, 24, 34].map((r) => (
            <ellipse
              key={r}
              cx={50}
              cy={50}
              rx={r}
              ry={r * 1.25}
              fill="none"
              vectorEffect="non-scaling-stroke"
              className="stroke-rule"
              strokeDasharray="1 5"
            />
          ))}
          {placed.map((p) => (
            <line
              key={p.key}
              x1={50}
              y1={50}
              x2={p.x}
              y2={p.y}
              vectorEffect="non-scaling-stroke"
              className={cn(
                "transition-colors",
                glowing(p.key) ? "stroke-ember" : p.key === props.focus ? "stroke-ember/60" : "stroke-rule-strong",
              )}
              strokeWidth={glowing(p.key) ? 1.5 : 1}
              strokeDasharray={glowing(p.key) || p.key === props.focus ? undefined : "3 4"}
            />
          ))}
        </svg>
        <Core {...props} lookAt={lookAt} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[38%]" />
        {placed.map((p) => (
          <div
            key={p.key}
            className="absolute w-44 -translate-x-1/2 -translate-y-1/2 lg:w-48"
            style={{ left: `${p.x}%`, top: `${p.y}%` } as CSSProperties}
          >
            {glowing(p.key) ? (
              <span
                key={props.pulses[p.key]}
                aria-hidden="true"
                className="mind-flash pointer-events-none absolute -inset-1 rounded-lg border border-ember"
              />
            ) : null}
            {p.node}
          </div>
        ))}
        <p className="absolute bottom-3 left-4 font-mono text-[0.68rem] text-ink-faint">{t("home-mind-house")}</p>
        <p className="absolute right-4 bottom-3 font-mono text-[0.68rem] text-ink-faint">{t("home-mind-reach")}</p>
      </div>
      {/* the same map, stacked, on small screens */}
      <div className="grid gap-5 p-4 md:hidden [&>*]:min-w-0">
        <Core {...props} lookAt={lookAt} className="justify-self-center" />
        <Stack label={t("home-mind-house")} nodes={left} glowing={glowing} pulses={props.pulses} />
        <Stack label={t("home-mind-reach")} nodes={right} glowing={glowing} pulses={props.pulses} />
      </div>
    </section>
  );
}

function Stack({
  label,
  nodes,
  glowing,
  pulses,
}: {
  label: string;
  nodes: Omit<Placed, "x" | "y">[];
  glowing: (key: string) => boolean;
  pulses: Record<string, number>;
}) {
  if (!nodes.length) return null;
  return (
    <div>
      <p className="label-mono mb-2">{label}</p>
      <ul className="grid gap-2 border-l border-dashed border-rule-strong pl-3">
        {nodes.map((n) => (
          <li key={n.key} className="relative min-w-0">
            <span aria-hidden="true" className="absolute top-1/2 -left-3 h-px w-3 bg-rule-strong" />
            {glowing(n.key) ? (
              <span
                key={pulses[n.key]}
                aria-hidden="true"
                className="mind-flash pointer-events-none absolute -inset-1 rounded-lg border border-ember"
              />
            ) : null}
            {n.node}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The agent: its figure looking toward what it attends to, its name, its state, and what it says. */
function Core({
  agent,
  state,
  calm,
  pulses,
  now,
  line,
  lookAt,
  className,
}: MindProps & { lookAt?: { x: number; y: number }; className?: string }) {
  const t = useT();
  const rippling = now - (pulses.agent ?? 0) < 1_600;
  return (
    <div className={cn("grid w-64 justify-items-center gap-2 text-center", className)}>
      <Link
        to="/journal"
        className="group relative grid justify-items-center gap-1.5 rounded-md"
        aria-label={t("home-mind-core", { agent: agent.name, state: t(`home-state-${state}`) })}
      >
        <span className="relative grid place-items-center rounded-full bg-paper p-2">
          {rippling ? (
            <span
              key={pulses.agent}
              aria-hidden="true"
              className="mind-ripple absolute inset-0 rounded-full border border-ember"
            />
          ) : null}
          <AgentFigure state={state} size="lg" lookAt={lookAt} className="lg:size-28" />
        </span>
        <span className="font-serif text-[1.65rem] leading-none text-ink group-hover:text-ember">{agent.name}</span>
        <span className="inline-flex items-center gap-1.5 font-mono text-[0.68rem] text-ink-muted">
          <span
            aria-hidden="true"
            className={cn("size-1.5 rounded-full", STATE_TONE[state], state !== "idle" && "mind-breathe")}
          />
          {t(`home-state-${state}`)}
          {agent.status === "degraded" ? <span className="text-amber">· {t("home-state-degraded")}</span> : null}
        </span>
      </Link>
      {line ? (
        <p
          aria-live="polite"
          className={cn(
            "relative max-w-64 rounded-md border border-rule bg-paper px-3 py-2 text-[0.85rem] leading-snug text-pretty text-ink",
            "before:absolute before:-top-1.5 before:left-1/2 before:size-3 before:-translate-x-1/2 before:rotate-45 before:border-t before:border-l before:border-rule before:bg-paper",
            calm && state === "idle" && "text-ink-muted",
          )}
        >
          {line}
        </p>
      ) : null}
    </div>
  );
}

function NodeFrame({ link, label, children }: { link: LinkProps; label: string; children: ReactNode }) {
  return (
    <Link
      {...link}
      aria-label={label}
      className="relative block rounded-md border border-rule bg-paper-raised/95 px-3 py-2 shadow-[0_1px_0_var(--rule)] hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ember"
    >
      {children}
    </Link>
  );
}

const initials = (p: Person) => p.name.slice(0, 1).toUpperCase();

function leftNodes({ rooms, away }: MindProps): Omit<Placed, "x" | "y">[] {
  const nodes = rooms.map((r) => ({ key: r.key, node: <Room room={r} /> }));
  if (away.length) nodes.push({ key: "away", node: <Away people={away} /> });
  return nodes;
}

function Room({ room: r }: { room: RoomNode }) {
  const t = useT();
  const label = t("home-room-label", {
    room: r.room,
    people: r.people.map((p) => p.name).join(", ") || t("home-room-nobody"),
    devices: r.satellites.length,
  });
  return (
    <NodeFrame link={{ to: "/journal", search: { room: r.room } }} label={label}>
      <span className="flex items-center gap-1.5">
        <House className="size-3.5 text-ink-faint" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate font-serif text-[0.98rem] text-ink">{r.room}</span>
        {r.satellites.map((s) => (
          <span
            key={s.id}
            aria-hidden="true"
            className={cn("size-2 rounded-[1px]", s.connected ? "bg-sage" : "border border-ink-faint")}
          />
        ))}
      </span>
      <span className="mt-1 flex min-h-5 items-center gap-1">
        {r.people.length ? (
          r.people.map((p) => (
            <span
              key={p.id}
              aria-hidden="true"
              className="grid size-5 place-items-center rounded-full bg-ink font-mono text-[0.62rem] text-paper"
            >
              {initials(p)}
            </span>
          ))
        ) : (
          <span className="font-mono text-[0.66rem] text-ink-faint">{t("home-room-nobody")}</span>
        )}
      </span>
    </NodeFrame>
  );
}

function Away({ people }: { people: Person[] }) {
  const t = useT();
  const names = people.map((p) => p.name).join(", ");
  return (
    <NodeFrame link={{ to: "/people" }} label={t("home-away-label", { names })}>
      <span className="font-mono text-[0.68rem] text-ink-muted">{t("home-away")}</span>
      <span className="mt-0.5 block truncate text-sm text-ink">{names}</span>
    </NodeFrame>
  );
}

function rightNodes({ reach }: MindProps): Omit<Placed, "x" | "y">[] {
  if (!reach) return [];
  const nodes: Omit<Placed, "x" | "y">[] = [];
  if (reach.channels.length) nodes.push({ key: "channels", node: <Channels reach={reach} /> });
  for (const task of reach.tasks.slice(0, 3)) nodes.push({ key: `task:${task.id}`, node: <TaskNode task={task} /> });
  if (reach.watches.length) nodes.push({ key: "watches", node: <Watches reach={reach} /> });
  if (reach.connections.length) nodes.push({ key: "connections", node: <Connections reach={reach} /> });
  return nodes;
}

function Channels({ reach }: { reach: Reach }) {
  const t = useT();
  const names = reach.channels.map((c) => c.name).join(", ");
  return (
    <NodeFrame link={{ to: "/system" }} label={t("home-channels-label", { names })}>
      <span className="flex items-center gap-1.5">
        <MessagesSquare className="size-3.5 text-ink-faint" aria-hidden="true" />
        <span className="flex-1 text-sm text-ink">{t("home-channels")}</span>
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-2">
        {reach.channels.map((c) => (
          <span key={c.id} className="inline-flex items-center gap-1 font-mono text-[0.66rem] text-ink-muted">
            <KindMark kind={c.brand ?? c.name} className="size-3" label={false} />
            <span
              aria-hidden="true"
              className={cn(
                "size-1.5 rounded-full",
                c.health === "ok" ? "bg-sage" : c.health === "down" ? "bg-brick" : "bg-amber",
              )}
            />
          </span>
        ))}
      </span>
    </NodeFrame>
  );
}

function TaskNode({ task }: { task: Reach["tasks"][number] }) {
  const t = useT();
  const brand = brandOf(task.executor);
  return (
    <NodeFrame
      link={{ to: "/tasks/$taskId", params: { taskId: task.id } }}
      label={t("home-task-label", { objective: task.objective, steps: task.steps.length })}
    >
      <span className="flex items-center gap-1.5">
        <Workflow className="size-3.5 text-kind-task" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-sm text-ink">{task.objective}</span>
      </span>
      <span className="mt-1 flex items-center gap-1.5 font-mono text-[0.66rem] text-ink-muted">
        {brand ? <BrandMark brand={brand} className="size-3" label={false} /> : null}
        <span className="flex gap-0.5" aria-hidden="true">
          {task.steps.slice(-8).map((_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: one tick per step
            <span key={i} className="h-2 w-1 bg-kind-task/70" />
          ))}
          <span className="mind-breathe h-2 w-1 bg-kind-task" />
        </span>
        {t("home-task-steps", { count: task.steps.length })}
      </span>
    </NodeFrame>
  );
}

function Watches({ reach }: { reach: Reach }) {
  const t = useT();
  return (
    <NodeFrame link={{ to: "/watches" }} label={t("home-watches-label", { count: reach.watches.length })}>
      <span className="flex items-center gap-1.5">
        <Radar className="size-3.5 text-kind-watch" aria-hidden="true" />
        <span className="flex-1 text-sm text-ink">{t("home-watches", { count: reach.watches.length })}</span>
      </span>
      <span className="mt-0.5 block truncate font-mono text-[0.66rem] text-ink-muted">{reach.watches[0]?.what}</span>
    </NodeFrame>
  );
}

function Connections({ reach }: { reach: Reach }) {
  const t = useT();
  const troubled = reach.connections.filter((c) => c.status !== "connected").length;
  return (
    <NodeFrame
      link={{ to: "/connections" }}
      label={t("home-connections-label", { count: reach.connections.length, troubled })}
    >
      <span className="flex items-center gap-1.5">
        <Cable className="size-3.5 text-ink-faint" aria-hidden="true" />
        <span className="flex-1 text-sm text-ink">{t("home-connections", { count: reach.connections.length })}</span>
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-1.5">
        {reach.connections.map((c) => (
          <span key={c.id} className="relative inline-flex">
            <KindMark kind={c.brand ?? c.kind} className="size-3 text-ink-muted" label={false} />
            <span
              aria-hidden="true"
              className={cn(
                "absolute -right-0.5 -bottom-0.5 size-1.5 rounded-full",
                c.status === "connected" ? "bg-sage" : c.status === "needs_reauth" ? "bg-amber" : "bg-brick",
              )}
            />
          </span>
        ))}
      </span>
    </NodeFrame>
  );
}
