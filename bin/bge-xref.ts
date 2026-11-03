/**
 * bge-xref.ts — auto cross-reference fleet todos against the estate code corpus.
 *
 * The architect's ask (2026-11-03): "we have our files in a bge or argos — we
 * can auto cross-ref and point the agent to the most relevant set of files."
 *
 * Two-stage hybrid, estate doctrine (same pattern as LSP semanticRank):
 *   1. BM25 recall  — query argos `pens-corpus` (35181 docs, ax_path absolute)
 *                     over the todo title+body → top-50 file candidates
 *   2. bge re-rank  — embed the todo query + each candidate's text (SERIAL,
 *                     freeinference full-answer invariant + 1 retry — the
 *                     2026-11-03 race fix, tau 4b6a7eae19) → cosine rank
 *                     → top-N file paths written back as a `touches:` footer
 *                     in the todo .md. The squawk board daemon (v2.0.0,
 *                     watches todo/) picks the edit up as an update.
 *
 * Usage: bun bin/bge-xref.ts [--all | --todo <file>] [--top 5] [--force]
 * Idempotent: skips todos that already carry a `touches:` footer unless
 * --force. Point an agent at a board item and the files it most likely touches
 * are right there in the footer.
 */
import { cosine, embedMany } from "/home/toxic/pens/barn/products/forge/hf/hf";

const ARGOS = "http://127.0.0.1:9200";
const INDEX = "pens-corpus";
const PENS_ROOT = "/home/toxic/pens";
/** The squawk daemon's SSOT board dir (hardcoded in bun/index.ts — ranch/squawk/todo). */
const TODO_DIR = "/home/toxic/pens/ranch/squawk/todo";
const BGE_DIM = 1024;
const FOOTER = "### bge-xref";

function trunc(text: string, n = 400): string {
	const t = text.trim().replace(/\s+/g, " ");
	return t.length > n ? `${t.slice(0, n)}…` : t;
}

/** Serial full-answer embed — never parallel batches (freeinference race). */
async function embedFull(inputs: string[]): Promise<number[][]> {
	for (let attempt = 0; attempt < 2; attempt++) {
		const vecs = await embedMany(inputs);
		if (vecs.length === inputs.length && vecs.every(v => v.length === BGE_DIM)) return vecs;
		if (attempt === 0) await new Promise(r => setTimeout(r, 900));
	}
	throw new Error(`embed short-answer after retry (${inputs.length} inputs)`);
}

/** ax_path `kind:readme/ranch/Foo/README.md` → /home/toxic/pens/ranch/Foo/README.md */
function realPath(ax: string, score: number): { path: string; score: number } {
	if (ax.startsWith("/")) return { path: ax, score };
	const p = ax.replace(/^kind:[a-z0-9_-]+\//i, "");
	return { path: p.startsWith("/") ? p : `${PENS_ROOT}/${p}`, score };
}

async function bm25Recall(query: string, size = 50) {
	const r = await fetch(`${ARGOS}/${INDEX}/_search`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		signal: AbortSignal.timeout(5000),
		body: JSON.stringify({
			size,
			// multi_match, NOT query_string: argos's ES-wire query_string parser
			// returns 0 hits even on sanitized input (measured 2026-11-03).
			query: { multi_match: { query: trunc(query, 200), fields: ["title^3", "text", "ax_path"] } },
			_source: ["ax_path", "text", "kind", "title"],
		}),
	});
	if (!r.ok) throw new Error(`argos ${r.status}: ${(await r.text()).slice(0, 120)}`);
	const d = await r.json();
	return (d.hits?.hits ?? []).map((h: any) => ({
		ax: h._source?.ax_path ?? h._source?.title ?? "",
		bm25: h._score ?? 0,
		text: (h._source?.text ?? h._source?.title ?? h._source?.ax_path ?? "").slice(0, 400),
	})).filter((c: any) => c.ax);
}

async function semanticRank(queryVec: number[], candidates: Array<{ ax: string; bm25: number; text: string }>, topN: number) {
	const vecs = await embedFull(candidates.map(c => trunc(c.text, 350)));
	// dedupe: estate-skills-hub + geode/azurite mirror the SAME skill docs under
	// different ax_paths — collapse to the canonical azurite copy, keep best score
	const key = (p: string) => {
		const k = p.replace(/^kind:[a-z0-9_-]+\//i, ""); // strip ax kind prefix FIRST
		return k
			.replace(/^\/home\/toxic\/pens\//, "")
			.replace(/^(estate\/estate-skills-hub|geode\/azurite)\/skills\//, "geode/azurite/skills/")
			.replace(/^geode\/azurite\/upstream\/skills-hub\//, "geode/azurite/skills/");
	};
	const seen = new Map<string, { ax: string; bm25: number; sem: number }>();
	for (const [i, c] of candidates.entries()) {
		const s = { ax: c.ax, bm25: c.bm25, sem: cosine(queryVec, vecs[i]) };
		const k = key(c.ax);
		const prev = seen.get(k);
		if (!prev || s.sem > prev.sem) seen.set(k, s);
	}
	return [...seen.values()]
		.sort((a, b) => b.sem - a.sem)
		.slice(0, topN)
		.map(c => realPath(c.ax, c.sem));
}

/** Read title + body from a todo .md. */
function todoText(file: string): string {
	let raw = "";
	try {
		raw = require("node:fs").readFileSync(file, "utf8");
	} catch { return ""; }
	const title = (raw.match(/^#\s+(.+)$/m)?.[1] ?? raw.split("\n")[0] ?? "").trim();
	const body = raw.replace(/^---\n[\s\S]*?\n---\n?/, "").replace(/^#\s+.+$/m, "").slice(0, 600);
	return trunc(`${title} — ${body}`, 500);
}

function hasXref(raw: string): boolean {
	return raw.includes(FOOTER) && raw.includes("touches:");
}

const fsx = require("node:fs") as typeof import("node:fs");

/**
 * One-stamp guarantee (2026-11-03): the hasXref skip alone has a TOCTOU hole —
 * two concurrent invocations can both pass the check before either writes, then
 * double-stamp. Every read→check→stamp cycle runs under an exclusive per-todo
 * lock (`<todo>.xref.lock`, O_EXCL); a crashed holder is stolen once stale
 * (>60s). The write itself is atomic (tmp + rename), so a torn footer can never
 * make a second run misdetect.
 */
async function withTodoLock<T>(todoFile: string, fn: () => Promise<T>): Promise<T> {
	const lockPath = `${todoFile}.xref.lock`;
	const lock = (): boolean => {
		try {
			const fd = fsx.openSync(lockPath, "wx");
			fsx.writeFileSync(fd, String(process.pid));
			fsx.closeSync(fd);
			return true;
		} catch {
			// stale holder? (crashed mid-stamp) — steal after 60s
			try {
				if (Date.now() - fsx.statSync(lockPath).mtimeMs > 60_000) {
					fsx.unlinkSync(lockPath);
					return lock();
				}
			} catch {}
			return false;
		}
	};
	for (let attempt = 0; attempt < 5; attempt++) {
		if (lock()) {
			try {
				return await fn();
			} finally {
				try { fsx.unlinkSync(lockPath); } catch {}
			}
		}
		await new Promise(r => setTimeout(r, 400));
	}
	throw new Error(`lock busy (5×400ms): ${lockPath} — another xref run is stamping this todo`);
}

/** Append/replace the footer — CALLER HOLDS the todo's exclusive lock. Atomic (tmp+rename). */
function stampUnderLock(file: string, hits: Array<{ path: string; score: number }>, force: boolean): boolean {
	const raw = fsx.readFileSync(file, "utf8");
	if (hasXref(raw) && !force) return false;
	let out = raw;
	const marker = raw.indexOf(FOOTER);
	if (marker !== -1) {
		// walk back over the old block's trailing lines to its `---` separator
		let cut = marker;
		const head = raw.slice(0, marker);
		const sep = head.lastIndexOf("\n---\n");
		if (sep !== -1) cut = sep + 1; // keep the line before `---`
		out = raw.slice(0, cut).replace(/\n+$/, "") + "\n";
	}
	const run = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
	const line = `${FOOTER} run=${run} (${new Date().toISOString()})\ntouches: ${hits.map(h => `${h.path} (${h.score.toFixed(2)})`).join(", ")}`;
	out = `${out}\n---\n${line}\n`;
	fsx.writeFileSync(`${file}.tmp`, out);
	fsx.renameSync(`${file}.tmp`, file); // atomic swap — never a torn footer
	return true;
}

async function main() {
	const args = process.argv.slice(2);
	const force = args.includes("--force");
	const topN = Number(args[args.indexOf("--top") + 1] ?? 5) || 5;

	let files: string[] = [];
	const todoIdx = args.indexOf("--todo");
	if (todoIdx !== -1) {
		files = [args[todoIdx + 1]];
	} else {
		const fs = require("node:fs");
		const { execSync } = require("node:child_process");
		// todos the board still has open or unknown
		const TOK = fs.existsSync("/home/toxic/.config/estate-chat-token") ? fs.readFileSync("/home/toxic/.config/estate-chat-token", "utf8").trim() : "";
		const r = await fetch("http://127.0.0.1:25120/v1/todo", { headers: { Authorization: `Bearer ${TOK}` }, signal: AbortSignal.timeout(3000) }).catch(() => null);
		const open = (r ? (await r.json()).todos ?? [] : []).filter((t: any) => !String(t.status ?? "").toLowerCase().includes("done"));
		files = open.map((t: any) => `${TODO_DIR}/${t.file}`).filter((f: string) => fs.existsSync(f));
	}

	let done = 0;
	for (const file of files) {
		if (!fsx.existsSync(file)) { console.log(`skip  ${file.split("/").pop()} (missing)`); continue; }
		const query = todoText(file);
		if (!query || query.length < 8) { console.log(`skip  ${file.split("/").pop()} (empty)`); continue; }
		// clone the refs chain into a lock-guarded single-stamp unit: the whole
		// read→recall→rank→stamp for THIS todo runs under its exclusive lock so
		// two invocations can never stamp the same todo twice, even concurrently.
		try {
			const stamped = await withTodoLock(file, async () => {
				const raw = fsx.readFileSync(file, "utf8");
				if (hasXref(raw) && !force) return false;
				const candidates = await bm25Recall(query, 50);
				if (!candidates.length) { console.log(`noHits ${file.split("/").pop()}`); return false; }
				const qvec = (await embedFull([query]))[0];
				const hits = await semanticRank(qvec, candidates, topN);
				stampUnderLock(file, hits, force);
				for (const h of hits) console.log(`        ${h.score.toFixed(3)} ${h.path.replace(PENS_ROOT + "/", "")}`);
				return true;
			});
			if (stamped) { console.log(`xref  ${file.split("/").pop()}`); done++; }
			else console.log(`skip  ${file.split("/").pop()} (has touches:)`);
		} catch (e) {
			console.log(`fail  ${file.split("/").pop()}: ${e instanceof Error ? e.message.slice(0, 90) : e}`);
		}
	}
	console.log(`done: ${done}/${files.length} todos xref'd`);
}

main().catch(e => { console.error(e); process.exit(1); });