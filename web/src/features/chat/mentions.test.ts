import { describe, expect, it } from "vitest";
import type { Mention } from "@/api";
import { find, matching } from "./mentions";

const mention = (kind: Mention["kind"], handle: string, label: string, aliases: string[] = []): Mention => ({
  kind,
  handle,
  label,
  aliases,
  detail: "",
  brand: null,
});

const DINING = mention("room", "dining-room", "Salle à manger", ["Salle à manger"]);
const GMAIL = mention("connection", "gmail", "mathis@gmail.com", ["google", "mathis"]);
const MATHIS = mention("person", "mathis", "Mathis", ["Mathis"]);
const ALL = [MATHIS, DINING, GMAIL];

describe("names written after @, read as the server reads them", () => {
  it("offers what a handle, or a word of any of its names, starts with, case and accents aside", () => {
    expect(matching(ALL, "SAL")).toEqual([DINING]);
    expect(matching(ALL, "mang")).toEqual([DINING]);
    expect(matching(ALL, "goo")).toEqual([GMAIL]);
    expect(matching(ALL, "")).toEqual(ALL);
  });

  it("finds a handle before any other name: @mathis is the person, not the account that answers to it too", () => {
    expect(find(ALL, "Mathis")).toBe(MATHIS);
    expect(find(ALL, "google")).toBe(GMAIL);
    expect(find(ALL, "salle-à-manger")).toBe(DINING);
    expect(find(ALL, "nobody")).toBeUndefined();
  });
});
