// Regenerate the typed API client from the backend's OpenAPI spec.
//
//   npm run gen:api     writes src/api/openapi.json and src/api/schema.d.ts
//   npm run check:api   fails if either committed file is out of date (CI)
//
// Needs uv (the backend's toolchain); no server or database is started.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "..");
const backend = path.resolve(frontend, "../backend");
const specPath = path.join(frontend, "src/api/openapi.json");
const typesPath = path.join(frontend, "src/api/schema.d.ts");
const check = process.argv.includes("--check");

const spec = execFileSync("uv", ["run", "--quiet", "python", "scripts/export_openapi.py"], {
  cwd: backend,
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const header =
  "// Generated from the backend's OpenAPI spec by `npm run gen:api`. Do not edit.\n\n";
const types = header + astToString(await openapiTS(JSON.parse(spec)));

const outputs = [
  [specPath, spec],
  [typesPath, types],
];

if (check) {
  const stale = outputs.filter(([p, text]) => !existsSync(p) || readFileSync(p, "utf8") !== text);
  if (stale.length) {
    console.error(
      "The API client is out of date with the backend. Run `npm run gen:api` in frontend/ and commit:\n" +
        stale.map(([p]) => "  " + path.relative(frontend, p)).join("\n"),
    );
    process.exit(1);
  }
  console.log("API client matches the backend.");
} else {
  for (const [p, text] of outputs) writeFileSync(p, text);
  console.log("Wrote src/api/openapi.json and src/api/schema.d.ts");
}
