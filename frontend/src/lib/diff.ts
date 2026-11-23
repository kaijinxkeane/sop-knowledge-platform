/**
 * Side-by-side line diff for comparing two versions of a note. Lines are
 * matched along the longest common subsequence; a removed run directly
 * followed by an added run is shown as changed lines, pair by pair.
 */
export type Row =
  | { kind: "same"; left: string; right: string; leftNo: number; rightNo: number }
  | { kind: "changed"; left: string; right: string; leftNo: number; rightNo: number }
  | { kind: "removed"; left: string; leftNo: number }
  | { kind: "added"; right: string; rightNo: number };

export type Stats = { added: number; removed: number; changed: number };

export function lineDiff(before: string, after: string): Row[] {
  const a = before.split("\n");
  const b = after.split("\n");
  // Trim the common start and end: most edits are small and local.
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length, endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--;
    endB--;
  }
  const ma = a.slice(start, endA), mb = b.slice(start, endB);

  const dp = Array.from({ length: ma.length + 1 }, () => new Uint32Array(mb.length + 1));
  for (let i = ma.length - 1; i >= 0; i--)
    for (let j = mb.length - 1; j >= 0; j--)
      dp[i]![j] = ma[i] === mb[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);

  const rows: Row[] = [];
  for (let k = 0; k < start; k++) rows.push({ kind: "same", left: a[k]!, right: b[k]!, leftNo: k + 1, rightNo: k + 1 });
  let removed: Row[] = [], added: Row[] = [];
  const flush = () => {
    const n = Math.min(removed.length, added.length);
    for (let k = 0; k < n; k++) {
      const r = removed[k] as Extract<Row, { kind: "removed" }>;
      const s = added[k] as Extract<Row, { kind: "added" }>;
      rows.push({ kind: "changed", left: r.left, right: s.right, leftNo: r.leftNo, rightNo: s.rightNo });
    }
    rows.push(...removed.slice(n), ...added.slice(n));
    removed = [];
    added = [];
  };
  let i = 0, j = 0;
  while (i < ma.length || j < mb.length) {
    if (i < ma.length && j < mb.length && ma[i] === mb[j]) {
      flush();
      rows.push({ kind: "same", left: ma[i]!, right: mb[j]!, leftNo: start + i + 1, rightNo: start + j + 1 });
      i++;
      j++;
    } else if (j >= mb.length || (i < ma.length && dp[i + 1]![j]! >= dp[i]![j + 1]!)) {
      removed.push({ kind: "removed", left: ma[i]!, leftNo: start + i + 1 });
      i++;
    } else {
      added.push({ kind: "added", right: mb[j]!, rightNo: start + j + 1 });
      j++;
    }
  }
  flush();
  for (let k = 0; endA + k < a.length; k++)
    rows.push({ kind: "same", left: a[endA + k]!, right: b[endB + k]!, leftNo: endA + k + 1, rightNo: endB + k + 1 });
  return rows;
}

export function stats(rows: Row[]): Stats {
  const s = { added: 0, removed: 0, changed: 0 };
  for (const r of rows) if (r.kind !== "same") s[r.kind]++;
  return s;
}

/** Long unchanged runs fold to a few lines of context around each change. */
export type Shown = { rows: Row[] } | { hidden: number; from: number };

export function fold(rows: Row[], context = 3): Shown[] {
  const keep = rows.map((r) => r.kind !== "same");
  const near = keep.map((_, i) => {
    for (let k = Math.max(0, i - context); k <= Math.min(rows.length - 1, i + context); k++) if (keep[k]) return true;
    return false;
  });
  const out: Shown[] = [];
  let i = 0;
  while (i < rows.length) {
    if (near[i]) {
      const chunk: Row[] = [];
      while (i < rows.length && near[i]) chunk.push(rows[i++]!);
      out.push({ rows: chunk });
    } else {
      const from = i;
      while (i < rows.length && !near[i]) i++;
      out.push({ hidden: i - from, from });
    }
  }
  return out;
}
