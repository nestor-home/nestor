import { describe, expect, it } from "vitest";
import { problems, usedSecrets } from "./config";
import { fresh } from "./db";
import { plugged } from "./instance";

/** The channel a journal entry, a task or an account names, as the file plugs it in: `voice` is the satellites'. */
const channelOf = (named: string) => {
  const channel = named.split(":")[0] ?? named;
  return channel === "voice" ? "satellites" : channel;
};

describe("the mock instance", () => {
  const db = fresh();
  const doc = db.config.document;
  const names = (slot: string) => plugged(doc).flatMap((p) => (p.slot === slot ? [p.name] : []));

  it("has a configuration Nestor accepts, whose vault keeps one secret nothing uses", () => {
    expect(problems(db.config, doc, {}, "en")).toEqual([]);
    const used = usedSecrets(doc);
    expect(Object.keys(db.config.vault).filter((name) => !(name in used))).toEqual(["github.token"]);
  });

  it("runs what the configuration plugs in, and three things need a look", () => {
    const configured = db.system.components.filter((c) => c.slot !== "satellite");
    expect(configured.map((c) => `${c.slot}/${c.name}`)).toEqual(plugged(doc).map((p) => `${p.slot}/${p.name}`));
    const unwell = db.system.components.filter((c) => c.health !== "started");
    expect(unwell.map((c) => [c.slot, c.name, c.health])).toEqual([
      ["tools", "recipes", "unavailable"],
      ["connector", "google", "degraded"],
      ["satellite", "reachy-office", "unavailable"],
    ]);
    expect(unwell.every((c) => c.health_detail)).toBe(true);
    expect(db.system.nestor.version).toBe(db.updates.running);
  });

  it("names only channels of the configuration: people's accounts, tasks, alerts, messages, the journal", () => {
    const channels = new Set(names("channel"));
    const named = [
      ...db.people.flatMap((p) => [...p.channel_accounts, ...(p.reach ? [p.reach] : [])]),
      ...[...db.tasks, ...db.alerts, ...db.confirmations].flatMap((x) => x.origin?.channel ?? []),
      ...db.tasks.flatMap((t) => t.thread.flatMap((turn) => turn.delivered?.channel ?? [])),
      ...[...db.messages.questions, ...db.messages.pending].flatMap((m) => m.channel ?? []),
      ...db.journal.flatMap((e) => e.item.channels),
      ...db.memories.flatMap((m) => m.learnt_in ?? []),
    ];
    expect([...new Set(named.map(channelOf))].filter((c) => !channels.has(c))).toEqual([]);
  });

  it("hands tasks to executors of the configuration, each known to Nestor's MCP server", () => {
    const executors = names("executor");
    expect([...new Set(db.tasks.map((t) => t.executor))].filter((e) => !executors.includes(e))).toEqual([]);
    expect(db.executors.executors.map((e) => e.name)).toEqual(executors);
  });

  it("connects accounts to connectors of the configuration, and waits for what its sources bring", () => {
    const connectors = names("connector");
    expect(db.connectors.map((c) => c.kind)).toEqual(connectors);
    expect(db.connections.filter((c) => !connectors.includes(c.kind))).toEqual([]);
    const brought = new Set([...db.connectors.flatMap((c) => c.inbound), ...db.inbound]);
    expect(db.alerts.flatMap((a) => a.kinds).filter((kind) => !brought.has(kind))).toEqual([]);
  });

  it("knows the people of the configuration, at home through the entities it ties them to", () => {
    const household = doc.household as { id: string; name: string }[];
    expect(db.people.map((p) => [p.id, p.name])).toEqual(household.map((p) => [p.id, p.name]));
    const tied = Object.keys((doc.home as { people: object }).people);
    expect(db.home?.people.filter((p) => p.entity).map((p) => p.person.id)).toEqual(tied);
  });
});
