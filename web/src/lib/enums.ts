/** Whether `value` is one of an enum's values, as the API's schema lists them (`*Values` of `schema.gen.ts`). */
export const oneOf = <T extends string>(values: readonly T[], value: unknown): value is T =>
  typeof value === "string" && (values as readonly string[]).includes(value);
