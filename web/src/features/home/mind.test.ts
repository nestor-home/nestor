import { describe, expect, it } from "vitest";
import type { Home } from "@/api";
import { home, people, satellites } from "@/mocks/fixtures";
import { liveItem } from "@/test/render";
import { marksOf, roomsOf } from "./mind";

const NOW = Date.parse("2026-10-30T15:00:00Z");
const at = (minutesAgo: number) => new Date(NOW - minutesAgo * 60_000).toISOString();

describe("the day's marks", () => {
  it("makes one mark per conversation, however many turns, and one per message delivered", () => {
    const items = [
      liveItem({ at: at(30), links: { session: "s1" }, people: [{ id: "lea", name: "Léa" }] }),
      liveItem({ at: at(29), type: "conversation.turn.assistant", links: { session: "s1" }, people: [] }),
      liveItem({ at: at(28), links: { session: "s1" }, people: [{ id: "jules", name: "Jules" }] }),
      liveItem({ at: at(10), type: "initiative.delivered", kind: "delivery", links: { delivery: "d1" } }),
      liveItem({ at: at(5), type: "agent.tool.called", kind: "tool" }),
    ];
    const marks = marksOf(items);
    expect(marks.map((m) => m.kind)).toEqual(["conversation", "delivery"]);
    expect(marks[0]?.count).toBe(3);
    expect(marks[0]?.people.map((p) => p.id)).toEqual(["lea", "jules"]);
  });
});

type Room = Home["rooms"][number];

describe("the rooms", () => {
  it("are the home system's rooms, with the satellites in them, who is there, or that someone is", () => {
    const answering = home();
    const [living, kitchen] = answering.rooms as [Room, Room];
    answering.rooms[1] = { ...kitchen, occupied: true }; // a sensor sees someone, nobody is placed there
    const rooms = roomsOf({
      people: people().map((p) => ({ ...p, connections: [], account: null })),
      satellites: satellites(),
      items: [],
      home: answering,
    });
    expect(rooms[0]).toMatchObject({ room: living.name, journal: expect.any(String) });
    expect(rooms[0]?.people.map((p) => p.id)).toEqual(["mathis", "jules"]);
    expect(rooms[0]?.satellites.map((s) => s.id)).toEqual(["reachy-living-room"]);
    expect(rooms.find((r) => r.room === kitchen.name)).toMatchObject({ occupied: true, people: [], journal: null });
  });

  it("are the satellites' rooms without a home system", () => {
    const rooms = roomsOf({ people: [], satellites: satellites(), items: [] });
    expect(rooms.every((r) => r.occupied === null && r.journal === r.room)).toBe(true);
  });
});
