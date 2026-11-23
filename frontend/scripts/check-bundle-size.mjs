// Performance budget (frontend spec §10): initial JS under 300 KB gzipped.
// Counts the scripts index.html loads up front (entry + modulepreloads).
import { readFileSync } from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";

const BUDGET = 300 * 1024;
const dist = path.resolve(import.meta.dirname, "../dist");
const html = readFileSync(path.join(dist, "index.html"), "utf8");
const scripts = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.js)"/g)].map((m) => m[1]);
let total = 0;
for (const s of new Set(scripts)) {
  const size = gzipSync(readFileSync(path.join(dist, s))).length;
  total += size;
  console.log(`${(size / 1024).toFixed(1).padStart(7)} KB  ${s}`);
}
console.log(`${(total / 1024).toFixed(1).padStart(7)} KB  initial JS (gzip), budget ${BUDGET / 1024} KB`);
if (total > BUDGET) {
  console.error("Over the initial JS budget: code-split the new route or dependency.");
  process.exit(1);
}
