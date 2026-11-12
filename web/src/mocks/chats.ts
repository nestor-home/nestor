/**
 * The mock household's chats with its assistant, and how the mock answers a new message: word by word, a tool call
 * first when it is asked to act in the house, Markdown when it lists or compares.
 */
import type { ChatFile, ChatMessage, ChatTool } from "@/api";
import { fr } from "./french";

export interface MockChat {
  id: string;
  started_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

let position = 90_000; // the chats' entries, past the day's journal: their files are served by position
const next = () => ++position;

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

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
  const dinner = minutesAgo(18);
  const plant = minutesAgo(26 * 60);
  const voice = minutesAgo(3 * 24 * 60);
  const insurance = minutesAgo(9 * 24 * 60);
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
          tool: tool("homeassistant__HassTurnOn", { area: "kitchen", domain: ["light"] }, '{"success": true}', 0.4),
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
          tool: tool("schedule", { at: "Sunday 10:00", instruction: "Call grandma" }, "Scheduled s-12.", 0.2),
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
      updated_at: minutesAgo(9 * 24 * 60 - 40),
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
            ...tool("delegate", { executor: "hermes", task: "Read the contract" }, "Task 3f2a started.", 1.2),
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
        message("note", fr("task 3f2a completed", "tâche 3f2a terminée"), minutesAgo(9 * 24 * 60 - 40), "t5"),
        message(
          "assistant",
          fr(
            "Water damage is covered up to **€15,000**, with a €150 deductible. Leaks from appliances are included; a slow leak you could have seen is not.",
            "Le dégât des eaux est couvert jusqu'à **15 000 €**, avec une franchise de 150 €. Les fuites d'appareils sont incluses ; une fuite lente qu'on aurait pu voir ne l'est pas.",
          ),
          minutesAgo(9 * 24 * 60 - 40),
          "t5",
        ),
      ],
    },
  ];
}

/** The executors a message can name with `@`. */
export const MENTIONS = [
  {
    name: "hermes",
    description: fr(
      "Long tasks: searching the web, reading documents, following up on projects.",
      "Tâches longues : chercher sur le web, lire des documents, suivre des projets.",
    ),
    brand: "hermes",
  },
  {
    name: "codex",
    description: fr(
      "Code: reads a repository, changes it, runs its tests, opens a pull request.",
      "Code : lit un dépôt, le modifie, lance ses tests, ouvre une pull request.",
    ),
    brand: "openai",
  },
];

/** The mock's answer to `text`: a tool call first when it is asked to act, then words. */
export function answerTo(text: string, files: number): { tool: ChatTool | null; answer: string } {
  const words = text.toLocaleLowerCase();
  const named = MENTIONS.find((m) => words.includes(`@${m.name}`));
  if (named) {
    return {
      tool: {
        ...tool("delegate_task", { executor: named.name, objective: text }, "Task 7c1e started.", 0.6),
        state: "background",
      },
      answer: fr("It's in hand; I'll come back here when it's done.", "C'est lancé ; je reviens ici quand c'est fini."),
    };
  }
  if (/light|lamp|lumi|allum/.test(words)) {
    return {
      tool: tool("homeassistant__HassTurnOn", { area: "living room", domain: ["light"] }, '{"success": true}', 0.3),
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
