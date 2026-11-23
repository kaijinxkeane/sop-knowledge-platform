import { en, type MessageKey } from "./en";

export type { MessageKey };

/** Look up UI text; `{name}` placeholders are filled from `vars`. */
export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const text: string = en[key];
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, name: string) =>
    name in vars ? String(vars[name]) : m,
  );
}
