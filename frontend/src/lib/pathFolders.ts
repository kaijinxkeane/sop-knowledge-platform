/**
 * Onboarding paths from Library folders. Works only on documents the person
 * can already read (the Library list); the server re-checks every item.
 */
type DocLike = { id: string; title: string; vault_path: string; space?: string | null };

const parentOf = (path: string) => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
const SKIP = ["Help", "Inbox", "Drafts", "Handovers", "Projects"];
const skipped = (folder: string) => SKIP.some((s) => folder === s || folder.startsWith(`${s}/`));
const byTitle = <T extends DocLike>(a: T, b: T) => a.title.localeCompare(b.title);

/** Every folder (and parent folder) holding a readable document of this department. */
export function departmentFolders(docs: DocLike[], space: string): string[] {
  const out = new Set<string>();
  for (const d of docs) {
    if (d.space !== space) continue;
    for (let f = parentOf(d.vault_path); f && !skipped(f); f = parentOf(f)) out.add(f);
  }
  return [...out].sort((a, b) => a.localeCompare(b));
}

/** The department's documents in a folder and its subfolders, by title. */
export function docsIn<T extends DocLike>(docs: T[], space: string, folder: string): T[] {
  return docs.filter((d) => d.space === space && d.vault_path.startsWith(`${folder}/`)).sort(byTitle);
}

/** One step per subfolder (in name order, so "01 …", "02 …" keep their order);
 * documents directly in the folder come first. */
export function stepsFromFolder<T extends DocLike>(docs: T[], space: string, folder: string): { title: string; docs: T[] }[] {
  const inside = docsIn(docs, space, folder);
  const top = inside.filter((d) => parentOf(d.vault_path) === folder);
  const groups = new Map<string, T[]>();
  for (const d of inside) {
    if (parentOf(d.vault_path) === folder) continue;
    const sub = d.vault_path.slice(folder.length + 1).split("/")[0]!;
    groups.set(sub, [...(groups.get(sub) ?? []), d]);
  }
  const name = folder.slice(folder.lastIndexOf("/") + 1);
  return [
    ...(top.length ? [{ title: name, docs: top }] : []),
    ...[...groups.keys()].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((sub) => ({ title: sub, docs: groups.get(sub)! })),
  ];
}
