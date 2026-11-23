/**
 * Note metadata as a form (frontend spec §6), written back into the YAML
 * frontmatter with comments, field order and unknown fields kept.
 */
import { isScalar, parseDocument } from "yaml";
import { plainName, splitFrontmatter } from "@/lib/obsidian";

export type Meta = {
  title: string;
  doc_type: string;
  owner: string;
  programme: string;
  stage: string;
  review_cycle_days: string;
  sensitivity: string;
  status: string;
};

export const EDITABLE: (keyof Meta)[] = [
  "title",
  "doc_type",
  "owner",
  "programme",
  "stage",
  "review_cycle_days",
  "sensitivity",
];
const LINKED = new Set<keyof Meta>(["owner", "programme"]);

export const SENSITIVITIES = ["public", "internal", "restricted"] as const;
export const rank = (s: string) => {
  const i = (SENSITIVITIES as readonly string[]).indexOf(s);
  return i < 0 ? 2 : i; // unknown reads as restricted, like the server
};

function load(text: string) {
  const { frontmatter } = splitFrontmatter(text);
  const doc = parseDocument(frontmatter ?? "");
  return { doc, ok: !doc.errors.length, hasFrontmatter: frontmatter !== null };
}

export function readMeta(text: string): Meta | null {
  const { doc, ok } = load(text);
  if (!ok) return null;
  const get = (k: keyof Meta) => {
    const v = doc.get(k);
    if (v === null || v === undefined) return "";
    const s = String(v);
    return LINKED.has(k) ? (plainName(s) ?? s) : s;
  };
  return Object.fromEntries(
    [...EDITABLE, "status"].map((k) => [k, get(k as keyof Meta)]),
  ) as Meta;
}

/** The note text with the form's values written into its frontmatter. */
export function writeMeta(text: string, meta: Partial<Meta>): string {
  const { body } = splitFrontmatter(text);
  const { doc, ok, hasFrontmatter } = load(text);
  if (!ok) throw new Error("frontmatter is not valid YAML");
  for (const k of EDITABLE) {
    if (!(k in meta)) continue;
    const value = (meta[k] ?? "").trim();
    const before = readMeta(text)?.[k] ?? "";
    if (value === before) continue; // untouched fields keep their exact form
    if (!value) {
      if (doc.has(k)) doc.set(k, null);
      continue;
    }
    if (k === "review_cycle_days" && /^\d+$/.test(value)) doc.set(k, Number(value));
    else if (LINKED.has(k)) doc.set(k, `[[${value}]]`);
    else doc.set(k, value);
    const node = doc.get(k, true);
    if (isScalar(node) && typeof node.value === "string" && LINKED.has(k)) node.type = "QUOTE_DOUBLE";
  }
  const yaml = doc.toString().replace(/\n$/, "");
  return `---\n${yaml}\n---\n${hasFrontmatter ? body : "\n" + body}`;
}
