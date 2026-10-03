// Build script: compile Svelte 5 components -> JS, then bundle with Bun.
// Run: bun ui/build.ts  (or: mise run build)
import { compile } from "svelte/compiler";
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, basename } from "node:path";

const UI_DIR = new URL(".", import.meta.url).pathname;
const DIST_DIR = join(UI_DIR, "dist");

mkdirSync(DIST_DIR, { recursive: true });

// 1. Compile each .svelte file to JS (client-side, Svelte 5 runes)
//    Rewrite imports: ./X.svelte -> ./X.js, ./markdown -> ../markdown.js
const svelteFiles = readdirSync(UI_DIR).filter(f => f.endsWith(".svelte"));
for (const f of svelteFiles) {
  const src = readFileSync(join(UI_DIR, f), "utf8");
  const { js } = compile(src, { filename: f, generate: "client", dev: false });
  let code = js.code;
  // fix relative imports for the dist/ layout
  code = code.replace(/from\s+["']\.\/([\w-]+)\.svelte["']/g, 'from "./$1.js"');
  code = code.replace(/from\s+["']\.\/markdown["']/g, 'from "../markdown.js"');
  const outName = basename(f, ".svelte") + ".js";
  writeFileSync(join(DIST_DIR, outName), code);
  console.log(`compiled ${f} -> dist/${outName} (${code.length} bytes)`);
}

// 2. Bundle main.ts (+ compiled svelte JS + markdown.ts) with Bun
const result = await Bun.build({
  entrypoints: [join(UI_DIR, "main.ts")],
  outdir: DIST_DIR,
  minify: true,
  target: "browser",
  naming: "bundle.js",
});
if (!result.success) {
  console.error("bundle failed:");
  for (const log of result.logs) console.error(log.message);
  process.exit(1);
}
for (const out of result.outputs) {
  const text = await out.text();
  console.log(`bundled -> dist/bundle.js (${text.length} bytes)`);
}
console.log("build complete");
