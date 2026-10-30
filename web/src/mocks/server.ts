import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** The same mock API for component tests. */
export const server = setupServer(...handlers);
