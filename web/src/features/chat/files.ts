/** Files picked, dropped or pasted in the composer, as a message carries them. */
import type { ChatFileIn } from "@/api";

export const FILE_LIMIT = 20 * 1024 * 1024; // what the server takes, per file
export const FILES_PER_MESSAGE = 10;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]); // what the model can look at

export interface PendingFile {
  id: string;
  file: ChatFileIn;
  size: number;
  preview: string | null; // a picture's data URL, shown before it is sent
}

export function kindOf(type: string): ChatFileIn["kind"] {
  if (IMAGE_TYPES.has(type)) return "image";
  if (type.startsWith("audio/")) return "audio";
  return "file";
}

/** A file as it is sent, read once: its bytes in base64, and its preview when it is a picture. */
export async function pending(blob: Blob, kind: ChatFileIn["kind"], name: string | null): Promise<PendingFile> {
  const url = await dataUrl(blob);
  const type = blob.type.split(";")[0] || "application/octet-stream";
  return {
    id: crypto.randomUUID(),
    file: { kind, media_type: type, name, data: url.slice(url.indexOf(",") + 1) },
    size: blob.size,
    preview: kind === "image" ? url : null,
  };
}

function dataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
