/**
 * Edit clashes (frontend spec §6): three-way merge by block.
 *
 * base   = the note as it was when this person opened it
 * mine   = what they want to save
 * theirs = what is saved now (someone else saved in between)
 *
 * Each file is cut into chunks: the frontmatter, then each top-level markdown
 * block with the spacing after it. A chunk changed on one side only takes that
 * side automatically; a chunk changed differently on both sides is a clash the
 * person settles by choosing "theirs" or "yours". Nothing is merged by a model.
 */
import { splitFrontmatter } from "@/lib/obsidian";
import { blocks } from "./preserve";

export type Part = { kind: "same"; text: string } | { kind: "clash"; mine: string; theirs: string };

export function chunks(text: string): string[] {
  const { body } = splitFrontmatter(text);
  const head = text.slice(0, text.length - body.length);
  const bs = blocks(body);
  if (!bs.length) return [head + body].filter(Boolean);
  const out = [head + body.slice(0, bs[0]!.start)];
  bs.forEach((b, i) => out.push(body.slice(b.start, i + 1 < bs.length ? bs[i + 1]!.start : body.length)));
  return out.filter((c, i) => i > 0 || c !== "");
}

/** base index -> other index, along the longest common subsequence. */
function lcs(a: string[], b: string[]): Map<number, number> {
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
  const m = new Map<number, number>();
  for (let i = 0, j = 0; i < a.length && j < b.length; ) {
    if (a[i] === b[j]) m.set(i++, j++);
    else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) i++;
    else j++;
  }
  return m;
}

const join = (xs: string[]) => xs.join("");

export function merge3(baseText: string, mineText: string, theirsText: string): Part[] {
  const base = chunks(baseText);
  const mine = chunks(mineText);
  const theirs = chunks(theirsText);
  const toMine = lcs(base, mine);
  const toTheirs = lcs(base, theirs);
  const parts: Part[] = [];
  const push = (p: Part) => {
    const last = parts[parts.length - 1];
    if (p.kind === "same" && last?.kind === "same") last.text += p.text;
    else if (p.kind === "clash" || p.text) parts.push(p);
  };
  let b = 0, m = 0, t = 0;
  while (b < base.length || m < mine.length || t < theirs.length) {
    if (b < base.length && toMine.get(b) === m && toTheirs.get(b) === t) {
      push({ kind: "same", text: base[b]! });
      b++;
      m++;
      t++;
      continue;
    }
    // The next base chunk both sides kept; everything before it is one hunk.
    let next = b;
    while (next < base.length && !(toMine.has(next) && toTheirs.has(next))) next++;
    const endM = next < base.length ? toMine.get(next)! : mine.length;
    const endT = next < base.length ? toTheirs.get(next)! : theirs.length;
    const o = join(base.slice(b, next));
    const a = join(mine.slice(m, endM));
    const c = join(theirs.slice(t, endT));
    if (a === c || c === o) push({ kind: "same", text: a });
    else if (a === o) push({ kind: "same", text: c });
    else parts.push({ kind: "clash", mine: a, theirs: c });
    b = next;
    m = endM;
    t = endT;
  }
  return parts;
}

export type Choice = "mine" | "theirs";

export function resolve(parts: Part[], choices: Choice[]): string {
  let k = 0;
  return parts
    .map((p) => (p.kind === "same" ? p.text : choices[k++] === "theirs" ? p.theirs : p.mine))
    .join("");
}

export const clashCount = (parts: Part[]) => parts.filter((p) => p.kind === "clash").length;
