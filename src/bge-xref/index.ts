/**
 * index.ts — bge-xref orchestration: CLI wiring + the lock-guarded single-stamp
 * loop over open board todos.
 *
 * The whole read→recall→rank→stamp cycle for ONE todo runs under its
 * exclusive lock (lock.ts) so two invocations can never stamp the same todo
 * twice, even concurrently. Idempotent by default (skips already-stamped
 * todos); `--force` re-stamps once under the lock.
 *
 * Usage: bun bin/bge-xref.ts [--todo <file>] [--top N] [--force]
 */
import { existsSync, readFileSync } from "node:fs";
import { bm25Recall } from "./argos";
import { embedCached } from "./embed";
import { withFileLock } from "./lock";
import { semanticRank } from "./rerank";
import { hasXref, stampUnderLock, FOOTER } from "./stamp";
import { todoText, resolveTodoFiles } from "./todos";

const PENS_ROOT = "/home/toxic/pens";
const RECALL_SIZE = 50;

export interface CliArgs {
	todo?: string;
	topN: number;
	force: boolean;
}

export function parseArgs(argv: string[]): CliArgs {
	const force = argv.includes("--force");
	const todoIdx = argv.indexOf("--todo");
	const topN = Number(argv[argv.indexOf("--top") + 1] ?? 5) || 5;
	return { todo: todoIdx !== -1 ? argv[todoIdx + 1] : undefined, topN, force };
}

/** Xref one todo file; returns true when stamped. Never stamps twice under the lock. */
export async function xrefTodo(file: string, { topN, force }: CliArgs): Promise<boolean> {
	if (!existsSync(file)) throw new Error(`missing: ${file}`);
	const query = todoText(file);
	if (!query || query.length < 8) throw new Error(`empty todo text: ${file}`);

	return withFileLock(file, async () => {
		if (hasXref(readFileSync(file, "utf8")) && !force) return false;
		const candidates = await bm25Recall(query, RECALL_SIZE);
		if (candidates.length === 0) throw new Error("no corpus hits");
		const [qvec] = await embedCached([query]);
		const hits = await semanticRank(qvec, candidates, topN, PENS_ROOT);
		stampUnderLock(file, hits, { force });
		return true;
	});
}

export async function main(): Promise<void> {
	const cli = parseArgs(process.argv.slice(2));
	const files = await resolveTodoFiles(cli.todo);
	let done = 0;

	for (const file of files) {
		const base = file.split("/").pop() ?? file;
		try {
			const stamped = await xrefTodo(file, cli);
			if (stamped) {
				done++;
				console.log(`xref  ${base}`);
				const raw = readFileSync(file, "utf8");
				const tag = raw.split("\n").find(l => l.startsWith("touches:"));
				if (tag) for (const hit of tag.slice(9).split(", ")) console.log(`        ${hit.replace(PENS_ROOT + "/", "")}`);
			} else {
				console.log(`skip  ${base} (has ${FOOTER} touches:)`);
			}
		} catch (e) {
			console.log(`fail  ${base}: ${e instanceof Error ? e.message.slice(0, 90) : String(e)}`);
		}
	}
	console.log(`done: ${done}/${files.length} todos xref'd`);
}

if (import.meta.main) {
	main().catch(e => {
		console.error(e);
		process.exit(1);
	});
}