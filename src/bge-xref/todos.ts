/**
 * todos.ts — fleet board discovery + todo text extraction.
 *
 * The squawk daemon (v2.0.0) hardcodes its board SSOT dir in bun/index.ts:
 * `/home/toxic/pens/ranch/squawk/todo`. `products/squawk/todo/` is a STALE
 * 91-file remnant from an earlier migration (2026-11-03 measurement) — never
 * treat it as the board. Open = board status that does not include "done".
 */
import { readFileSync, existsSync } from "node:fs";
import { trunc } from "./trunc";

export const TODO_DIR = process.env.SQUAWK_TODO_DIR ?? "/home/toxic/pens/ranch/squawk/todo";
const BOARD_URL = process.env.SQUAWK_BOARD_URL ?? "http://127.0.0.1:25120/v1/todo";
const BOARD_TOKEN_PATH = "/home/toxic/.config/estate-chat-token";

/** Read title + body from a todo .md (title = first H1 or first line). */
export function todoText(file: string): string {
	let raw = "";
	try {
		raw = readFileSync(file, "utf8");
	} catch {
		return "";
	}
	const title = (raw.match(/^#\s+(.+)$/m)?.[1] ?? raw.split("\n")[0] ?? "").trim();
	const body = raw.replace(/^---\n[\s\S]*?\n---\n?/, "").replace(/^#\s+.+$/m, "").slice(0, 600);
	return trunc(`${title} — ${body}`, 500);
}

interface BoardTodo {
	file: string;
	status?: string;
	title?: string;
}

/** Todos the board still has open or unknown (status not containing "done"). */
export async function openBoardTodos(): Promise<BoardTodo[]> {
	let token = "";
	try {
		token = readFileSync(BOARD_TOKEN_PATH, "utf8").trim();
	} catch {}
	const r = await fetch(BOARD_URL, {
		headers: { Authorization: `Bearer ${token}` },
		signal: AbortSignal.timeout(3000),
	}).catch(() => null);
	if (!r) return [];
	const d = (await r.json()) as { todos?: BoardTodo[] };
	return (d.todos ?? []).filter(t => !String(t.status ?? "").toLowerCase().includes("done"));
}

/** Resolve board items to existing todo file paths (--all) or the explicit one (--todo). */
export async function resolveTodoFiles(todoArg: string | undefined): Promise<string[]> {
	if (todoArg) {
		return existsSync(todoArg) ? [todoArg] : [];
	}
	const open = await openBoardTodos();
	return open
		.map(t => `${TODO_DIR}/${t.file}`)
		.filter(f => existsSync(f));
}