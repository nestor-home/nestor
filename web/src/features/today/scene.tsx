import type { NestorController } from "@nestor-home/character";
import { RadioTower, Video } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Person } from "@/api";
import { AgentFigure, type FigureState } from "@/components/agent-figure";
import { Dither } from "@/components/dither";
import { Pebble } from "@/components/marks";
import type { RoomNode } from "@/features/today/mind";
import { useT } from "@/i18n";
import { capital, cn } from "@/lib/utils";
import { orbOf, phaseOf } from "./sky";

const LIVE = { saccades: true };

/**
 * The household right now, as one picture: the sky of the hour, the agent and what it says, the rooms
 * with a light in each one where someone is, and who is out. Each room opens.
 */
export function Scene({
  now,
  date,
  greeting,
  agent,
  state,
  stateLabel,
  line,
  rooms,
  home,
  away,
  focus,
  onRoom,
}: {
  now: Date;
  date: string;
  greeting: string;
  agent: string;
  state: FigureState;
  stateLabel: string;
  line: string;
  rooms: RoomNode[];
  home: Person[];
  away: Person[];
  focus: string | null;
  onRoom: (room: RoomNode) => void;
}) {
  const t = useT();
  const controller = useRef<NestorController | null>(null);
  const [ready, setReady] = useState(false);
  // it looks toward the room it attends to
  useEffect(() => {
    if (!ready) return;
    const target = focus ? document.querySelector(`[data-room="${CSS.escape(focus)}"]`) : null;
    if (target) controller.current?.lookAt(target);
    else controller.current?.center();
  }, [focus, ready]);
  return (
    <section className="sky" data-phase={phaseOf(now)} aria-labelledby="hello">
      <Dither
        shape="ramp-down"
        from={0.42}
        to={0}
        dot={3}
        className="absolute inset-0 -z-10 text-(--sky-grain) opacity-35"
      />
      <span aria-hidden="true" className="sky-orb" style={orbOf(now)} />
      <div
        className={cn(
          "grid items-end gap-x-10 gap-y-8 px-5 pt-7 sm:px-8 sm:pt-9",
          rooms.length ? "lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]" : "",
        )}
      >
        <div className="flex items-end gap-3 lg:pb-1">
          <AgentFigure
            state={state}
            size="lg"
            live={LIVE}
            ground
            label={t("home-figure-label", { agent, state: stateLabel })}
            className="shrink-0"
            onReady={(c) => {
              controller.current = c;
              setReady(true);
            }}
          />
          <p
            aria-live="polite"
            className="mb-8 line-clamp-5 max-w-[22rem] rounded-2xl sm:mb-12 rounded-bl-sm bg-paper-raised px-4 py-3 text-lead leading-snug text-ink shadow-lg"
          >
            <span className="mb-0.5 block text-meta font-medium text-ink-muted">
              {agent} · {stateLabel}
            </span>
            {line}
          </p>
        </div>
        {rooms.length ? <Rooms rooms={rooms} focus={focus} onRoom={onRoom} /> : null}
      </div>
      <div className="sky-ground flex flex-wrap items-end justify-between gap-x-10 gap-y-5 px-5 pt-5 pb-6 sm:px-8">
        <div className="min-w-0">
          <p className="text-body text-white/65 first-letter:uppercase">{date}</p>
          <h1 id="hello" className="mt-1 text-[clamp(1.9rem,4.4vw,2.9rem)] leading-[1.05]">
            {greeting}
          </h1>
        </div>
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {home.length ? <Group label={t("home-at-home")} people={home} /> : null}
          {away.length ? <Group label={t("home-away")} people={away} away /> : null}
        </div>
      </div>
    </section>
  );
}

/**
 * The rooms, whatever the home is (a studio, a flat, three floors): those where someone is come first, lit
 * and large; the quiet ones follow as small chips, the rest behind a count.
 */
function Rooms({
  rooms,
  focus,
  onRoom,
}: {
  rooms: RoomNode[];
  focus: string | null;
  onRoom: (room: RoomNode) => void;
}) {
  const t = useT();
  const [all, setAll] = useState(false);
  const isLit = (r: RoomNode) => r.people.length > 0 || r.occupied === true;
  const lit = rooms.filter(isLit);
  const quiet = rooms.filter((r) => !isLit(r));
  const shown = all ? quiet : quiet.slice(0, QUIET_SHOWN);
  const devices = (r: RoomNode) =>
    r.satellites.map((s) => {
      const Icon = s.films ? Video : RadioTower;
      return (
        <Icon
          key={s.id}
          aria-hidden="true"
          className={cn("size-3.5 shrink-0", s.connected === false ? "text-brick" : "opacity-70")}
        />
      );
    });
  const focused = (r: RoomNode) => focus === r.key;
  const label = (r: RoomNode) => {
    const who = r.people.length
      ? r.people.map((p) => p.name).join(", ")
      : r.occupied === null
        ? ""
        : t(r.occupied ? "home-room-someone" : "home-room-nobody");
    return who ? `${capital(r.room)} · ${who}` : capital(r.room);
  };
  return (
    <div className="grid content-end gap-2.5 pb-6">
      {lit.length ? (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2.5">
          {lit.map((r) => (
            <li key={r.key}>
              <button
                type="button"
                className="room h-full w-full"
                data-room={r.key}
                data-lit=""
                data-focus={focused(r) || undefined}
                aria-label={label(r)}
                onClick={() => onRoom(r)}
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 truncate text-body leading-tight font-semibold">{capital(r.room)}</span>
                  <span className="flex gap-1 pt-0.5">{devices(r)}</span>
                </span>
                <span className="flex min-h-7 flex-wrap items-center gap-1.5 text-meta">
                  {r.people.map((p) => (
                    <Pebble key={p.id} name={p.name} lit />
                  ))}
                  {r.people.length === 1 ? <span className="font-medium">{r.people[0]?.name}</span> : null}
                  {r.people.length ? null : t("home-room-someone")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {quiet.length ? (
        <ul className="flex flex-wrap gap-2">
          {shown.map((r) => (
            <li key={r.key}>
              <button
                type="button"
                className="room-chip"
                data-room={r.key}
                data-focus={focused(r) || undefined}
                aria-label={label(r)}
                onClick={() => onRoom(r)}
              >
                {capital(r.room)}
                {devices(r)}
              </button>
            </li>
          ))}
          {quiet.length > QUIET_SHOWN ? (
            <li>
              <button type="button" className="room-chip" aria-expanded={all} onClick={() => setAll((v) => !v)}>
                {all ? t("today-needs-fewer") : t("today-rooms-more", { count: quiet.length - QUIET_SHOWN })}
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

const QUIET_SHOWN = 6;

function Group({ label, people, away }: { label: string; people: Person[]; away?: boolean }) {
  return (
    <div>
      <p className="mb-1.5 text-meta text-white/65">{label}</p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1.5">
        {people.map((p) => (
          <li key={p.id} className="flex items-center gap-1.5 text-body">
            <Pebble name={p.name} away={away} lit={!away} />
            {p.name}
          </li>
        ))}
      </ul>
    </div>
  );
}
