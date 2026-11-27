/**
 * The mock household's chats with its assistant, and how the mock answers a new message: word by word, a tool call
 * first when it is asked to act in the house, Markdown when it lists or compares.
 */
import type { ChatFile, ChatMessage, ChatTool, Mention } from "@/api";
import { find, NAMED, nameKey } from "@/features/chat/mentions";
import { connections, minutes, ROOMS, ref, SHOWN, services, tasks } from "./fixtures";
import { fr } from "./french";
import { document, household, plugged } from "./instance";

export interface MockChat {
  id: string;
  started_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

let position = 90_000; // the chats' entries, past the day's journal: their files are served by position
const next = () => ++position;

function message(
  role: ChatMessage["role"],
  text: string,
  at: string,
  turn: string,
  extra: Partial<ChatMessage> = {},
): ChatMessage {
  const entry = next();
  return {
    position: entry,
    id: `ev-${entry}`,
    at,
    role,
    turn,
    text,
    interrupted: false,
    tool: null,
    ...extra,
    mentions: extra.mentions ?? [],
    files: (extra.files ?? []).map((f, index) => ({ ...f, position: entry, index })), // served with their entry
  };
}

function file(kind: ChatFile["kind"], extra: Partial<ChatFile> = {}): ChatFile {
  return {
    position: 0, // given by the message it comes with
    index: 0,
    kind,
    media_type: kind === "image" ? "image/png" : kind === "voice" ? "audio/ogg" : "application/pdf",
    size: kind === "image" ? 182_400 : kind === "voice" ? 24_600 : 412_000,
    name: null,
    transcript: null,
    ...extra,
  };
}

function tool(name: string, args: Record<string, unknown>, output: string, seconds: number): ChatTool {
  return { call: `call-${name}`, name, state: "done", arguments: args, output, duration_s: seconds };
}

export function chats(): MockChat[] {
  const dinner = minutes(18);
  const plant = minutes(26 * 60);
  const voice = minutes(3 * 24 * 60);
  const insurance = minutes(9 * 24 * 60);
  return [
    {
      id: "c-dinner",
      started_at: dinner,
      updated_at: dinner,
      messages: [
        message(
          "person",
          fr(
            "Turn on the kitchen lights and tell me what's left for dinner.",
            "Allume la cuisine et dis-moi ce qu'il reste pour le dîner.",
          ),
          dinner,
          "t1",
        ),
        message("tool", "", dinner, "t1", {
          tool: tool("intent__HassTurnOn", { area: "kitchen", domain: ["light"] }, '{"success": true}', 0.4),
        }),
        message("tool", "", dinner, "t1", {
          tool: tool(
            "recall",
            { query: "groceries this week" },
            "2026-11-10 Mathis bought leeks, eggs and comté.",
            0.1,
          ),
        }),
        message(
          "assistant",
          fr(
            "The kitchen lights are on.\n\nFrom what you bought on Tuesday, you could make:\n\n- **Leek and comté quiche**, about 45 minutes\n- **Leek omelette**, ready in 15\n\n| Dish | Time | Missing |\n| --- | --- | --- |\n| Quiche | 45 min | pastry |\n| Omelette | 15 min | nothing |",
            "La cuisine est allumée.\n\nAvec ce que vous avez acheté mardi, vous pourriez faire :\n\n- **Une quiche poireaux et comté**, environ 45 minutes\n- **Une omelette aux poireaux**, prête en 15\n\n| Plat | Temps | Il manque |\n| --- | --- | --- |\n| Quiche | 45 min | la pâte |\n| Omelette | 15 min | rien |",
          ),
          dinner,
          "t1",
        ),
      ],
    },
    {
      id: "c-dependencies",
      started_at: minutes(550),
      updated_at: minutes(520),
      messages: [
        message(
          "person",
          fr(
            "Ask @claude-code to update the dashboard's dependencies, then add a reminder to check it on @todo.",
            "Demande à @claude-code de mettre à jour les dépendances du tableau de bord, puis ajoute un rappel pour vérifier sur @todo.",
          ),
          minutes(550),
          "t6",
          { mentions: MENTIONS.filter((m) => m.handle === "claude-code" || m.handle === "todo") },
        ),
        message("tool", "", minutes(550), "t6", {
          tool: {
            ...tool(
              "start_task",
              { executor: "claude-code", title: "Dashboard dependencies", instruction: "Update the dependencies" },
              "Task c1a9de started.",
              0.6,
            ),
            state: "background",
          },
        }),
        message("tool", "", minutes(550), "t6", {
          tool: tool("todo_add", { title: "Check the dashboard" }, '{"id": "AAMk…"}', 0.7),
        }),
        message(
          "assistant",
          fr(
            "Claude Code is on it, and the reminder is in your To Do. I'll post the report here.",
            "Claude Code s'en occupe, et le rappel est dans ton To Do. Je poste le rapport ici.",
          ),
          minutes(550),
          "t6",
        ),
        message("note", fr("task c1a9 completed", "tâche c1a9 terminée"), minutes(520), "t7"),
        message(
          "assistant",
          fr(
            "Done: **12 dependencies** updated and the tests are green. Here is the report and a capture of the dashboard.",
            "C'est fait : **12 dépendances** à jour et les tests sont au vert. Voici le rapport et une capture du tableau de bord.",
          ),
          minutes(520),
          "t7",
          { files: [file("file", { name: "report.md", media_type: "text/markdown", size: 3_412 }), file("image")] },
        ),
      ],
    },
    {
      id: "c-plant",
      started_at: plant,
      updated_at: plant,
      messages: [
        message("person", fr("Why are its leaves turning yellow?", "Pourquoi ses feuilles jaunissent ?"), plant, "t2", {
          files: [file("image", { name: "plant.png" })],
        }),
        message(
          "assistant",
          fr(
            "It looks like a **pothos**. Yellow leaves near the base usually mean too much water. Let the soil dry on the top 3 cm between waterings, and keep it out of direct sun.",
            "On dirait un **pothos**. Des feuilles jaunes près de la base veulent souvent dire trop d'eau. Laissez sécher les 3 premiers centimètres de terre entre deux arrosages, et gardez-le hors du soleil direct.",
          ),
          plant,
          "t2",
        ),
      ],
    },
    {
      id: "c-voice",
      started_at: voice,
      updated_at: voice,
      messages: [
        message("person", "", voice, "t3", {
          files: [
            file("voice", {
              transcript: fr(
                "Remind me to call grandma on Sunday at ten.",
                "Rappelle-moi d'appeler mamie dimanche à dix heures.",
              ),
            }),
          ],
        }),
        message("tool", "", voice, "t3", {
          tool: tool(
            "create_alert",
            { title: "Call grandma", at: "Sunday 10:00", instruction: "Call grandma on Sunday", frequency: "once" },
            "Alert a-12 set.",
            0.2,
          ),
        }),
        message(
          "assistant",
          fr(
            "Done: Sunday at ten, I'll remind you to call her.",
            "C'est noté : dimanche à dix heures, je vous rappellerai de l'appeler.",
          ),
          voice,
          "t3",
          { files: [file("voice")] },
        ),
      ],
    },
    {
      id: "c-insurance",
      started_at: insurance,
      updated_at: minutes(9 * 24 * 60 - 40),
      messages: [
        message(
          "person",
          fr("What does this contract cover for water damage?", "Que couvre ce contrat pour un dégât des eaux ?"),
          insurance,
          "t4",
          {
            files: [file("file", { name: "home-insurance-2026.pdf" })],
          },
        ),
        message("tool", "", insurance, "t4", {
          tool: {
            ...tool(
              "start_task",
              { executor: "hermes", title: "Home insurance", instruction: "Read the contract" },
              "Task 3f2a1c started.",
              1.2,
            ),
            state: "background",
          },
        }),
        message(
          "assistant",
          fr(
            "Hermes is reading it; I'll come back here with the answer.",
            "Hermes le lit ; je reviens ici avec la réponse.",
          ),
          insurance,
          "t4",
        ),
        message("note", fr("task 3f2a completed", "tâche 3f2a terminée"), minutes(9 * 24 * 60 - 40), "t5"),
        message(
          "assistant",
          fr(
            "Water damage is covered up to **€15,000**, with a €150 deductible. Leaks from appliances are included; a slow leak you could have seen is not.",
            "Le dégât des eaux est couvert jusqu'à **15 000 €**, avec une franchise de 150 €. Les fuites d'appareils sont incluses ; une fuite lente qu'on aurait pu voir ne l'est pas.",
          ),
          minutes(9 * 24 * 60 - 40),
          "t5",
        ),
      ],
    },
  ];
}

/** The executors a message can name with `@`. */
const mention = (
  kind: Mention["kind"],
  handle: string,
  label: string,
  extra: Partial<Pick<Mention, "aliases" | "detail" | "brand">> = {},
): Mention => ({ kind, handle, label, aliases: [label], detail: "", brand: null, ...extra });

const ME = "mathis";

/**
 * What Mathis, who is signed in, may name in a message, as the server lists it from the instance: the people of the
 * household, the rooms of the home, his tasks, the executors of the file with what each is for, and the services of the
 * accounts he may use (his own and the household's, while connected), by the handle a message names them with.
 */
function mentions(): Mention[] {
  const doc = document();
  const mine = connections().filter((c) => c.owner === null || c.owner.id === ME);
  return [
    ...household(doc).map((p) => mention("person", p.id, p.name)),
    ...ROOMS.map(([id, name]) => mention("room", id.replaceAll(" ", "-"), name)),
    // what Home Assistant shows the assistant in those rooms
    ...Object.values(SHOWN).flatMap(({ devices }) =>
      devices.map((d) => mention("device", nameKey(d.name), d.name, { aliases: [d.name, ...d.aliases] })),
    ),
    // his own tasks, those not put away, by their title
    ...tasks()
      .filter((task) => task.owner?.id === ME && task.state !== "archived")
      .map((task) => mention("task", nameKey(task.title), task.title, { detail: task.executor })),
    ...plugged(doc)
      .filter((p) => p.slot === "executor")
      .map((p) =>
        mention("executor", p.name, p.name, { aliases: [], brand: p.brand, detail: String(p.entry.description) }),
      ),
    // named from where he stands: with the start of the address when two of the accounts he may use have the service
    ...mine.flatMap((c) =>
      services({ ...c, owner: ref(ME) }, mine).flatMap((service) =>
        service.handle
          ? [
              mention("connection", service.handle, c.account, {
                aliases: [c.kind, c.brand ?? c.kind, c.account.split("@")[0] ?? c.account, c.account],
                brand: c.brand,
              }),
            ]
          : [],
      ),
    ),
  ];
}

export const MENTIONS: Mention[] = mentions();

/** What a text names, as the server reads it. */
export function mentionedIn(text: string): Mention[] {
  const found = [...text.matchAll(NAMED)].map((m) => find(MENTIONS, (m[1] ?? "").slice(1)));
  return MENTIONS.filter((m) => found.includes(m));
}

/** The mock's answer to `text`: a tool call first when it is asked to act, then words. */
export function answerTo(text: string, files: number): { tool: ChatTool | null; answer: string } {
  const words = text.toLocaleLowerCase();
  const named = mentionedIn(text).find((m) => m.kind === "executor");
  if (named) {
    return {
      tool: {
        ...tool(
          "start_task",
          { executor: named.handle, title: fr("Asked in the chat", "Demandé dans le chat"), instruction: text },
          "Task 7c1e started.",
          0.6,
        ),
        state: "background",
      },
      answer: fr("It's in hand; I'll come back here when it's done.", "C'est lancé ; je reviens ici quand c'est fini."),
    };
  }
  if (/light|lamp|lumi|allum/.test(words)) {
    return {
      tool: tool("intent__HassTurnOn", { area: "living room", domain: ["light"] }, '{"success": true}', 0.3),
      answer: fr("Done, the living room lights are on.", "C'est fait, le salon est allumé."),
    };
  }
  if (files)
    return {
      tool: null,
      answer: fr("I've got it. What would you like me to do with it?", "Bien reçu. Que voulez-vous que j'en fasse ?"),
    };
  return {
    tool: null,
    answer: fr(
      "Here is what I can do from here:\n\n1. **Act in the house**: lights, heating, locks (those I confirm first)\n2. **Remember** what you tell me, and remind you of it\n3. **Read** photos, files and voice messages\n\nWhat would help?",
      "Voici ce que je peux faire d'ici :\n\n1. **Agir dans la maison** : lumières, chauffage, serrures (celles-ci après confirmation)\n2. **Retenir** ce que vous me dites, et vous le rappeler\n3. **Lire** photos, fichiers et messages vocaux\n\nQu'est-ce qui vous aiderait ?",
    ),
  };
}

export function chatMessage(role: ChatMessage["role"], text: string, turn: string, extra: Partial<ChatMessage> = {}) {
  return message(role, text, new Date().toISOString(), turn, extra);
}
