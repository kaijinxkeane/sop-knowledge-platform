import { en } from "@/i18n/en";
import { t, type MessageKey } from "@/i18n";

/**
 * Plain words for audit events. The log holds ids and outcomes only, so this
 * only relabels: action names become sentences, detail keys get labels, ids
 * of people become their names (when the viewer may list users), versions are
 * shortened. Unknown keys and actions still show, humanised.
 */

const has = (key: string): key is MessageKey => key in en;
const humanise = (s: string) => {
  const words = s.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const COMMIT = /^[0-9a-f]{40}$/i;

export type Namer = (id: string) => string | undefined;

export function actionText(action: string): string {
  const key = `auditAction.${action}`;
  return has(key) ? t(key) : humanise(action);
}

export function targetText(type: string | null | undefined, id: string | null | undefined, nameOf: Namer): string | null {
  if (!type && !id) return null;
  const typeKey = `auditTarget.${type}`;
  const label = type ? (has(typeKey) ? t(typeKey) : humanise(type)) : "";
  const who = id ? nameOf(id) : undefined;
  return [label, who ?? (id ? id.slice(0, 8) : "")].filter(Boolean).join(" · ");
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function scalar(v: unknown, nameOf: Namer): string {
  if (typeof v === "boolean") return v ? t("audit.yes") : t("audit.no");
  if (typeof v === "number") return v.toLocaleString();
  if (typeof v === "string") {
    if (COMMIT.test(v)) return t("audit.version", { id: v.slice(0, 7) });
    if (UUID.test(v)) return nameOf(v) ?? v.slice(0, 8);
    const valueKey = `auditValue.${v}`;
    return has(valueKey) ? t(valueKey) : v;
  }
  return JSON.stringify(v);
}

function value(key: string, v: unknown, nameOf: Namer): string | null {
  if (v === null || v === undefined || v === "") return null;
  if (key === "bytes" && typeof v === "number") return bytes(v);
  if (key === "minutes" && typeof v === "number") return `${v} min`;
  if (key === "months" && typeof v === "number") return `${v} months`;
  if (Array.isArray(v)) {
    if (v.length === 0) return "0";
    const shown = v.slice(0, 3).map((x) => scalar(x, nameOf));
    const list = shown.join(", ") + (v.length > 3 ? ` ${t("audit.more", { n: v.length - 3 })}` : "");
    // A list of ids reads better as a count with a preview.
    return v.every((x) => typeof x === "string" && UUID.test(x)) ? t("audit.countOf", { n: v.length, list }) : list;
  }
  if (typeof v === "object") {
    const parts = Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => {
        const shown = value(k, x, nameOf);
        return shown === null ? null : `${labelText(k)}: ${shown}`;
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  return scalar(v, nameOf);
}

export function labelText(key: string): string {
  const k = `auditKey.${key}`;
  return has(k) ? t(k) : humanise(key);
}

/** Label/value pairs for an event's details, skipping empty values. */
export function detailRows(details: Record<string, unknown> | null | undefined, nameOf: Namer): { label: string; value: string }[] {
  return Object.entries(details ?? {})
    .map(([k, v]) => ({ label: labelText(k), value: value(k, v, nameOf) }))
    .filter((r): r is { label: string; value: string } => r.value !== null);
}
