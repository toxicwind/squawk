/**
 * stamp.ts — the `touches:` footer writer for board todo files.
 *
 * Contract: CALLER HOLDS the target's exclusive lock (lock.ts). The write is
 * atomic (tmp + rename) so a torn footer can never make a second run
 * misdetect. A `run=<id>` is embedded so every stamp is auditable — a todo
 * stamped exactly once is provable at a glance.
 */
import { readFileSync, writeFileSync, renameSync, existsSync } from "node:fs";

export const FOOTER = "### bge-xref";
export const FOOTER_TAG = "touches:";

export function hasXref(raw: string): boolean {
	return raw.includes(FOOTER) && raw.includes(FOOTER_TAG);
}

export function xrefTaskWithFooter(file: string): boolean {
	return existsSync(file) && hasXref(readFileSync(file, "utf8"));
}

export interface StampOptions {
	force: boolean;
	pensRoot?: string;
}

/** Append/replace the footer. Atomic (tmp+rename). Returns true when stamped. */
export function stampUnderLock(
	file: string,
	hits: Array<{ path: string; score: number }>,
	{ force }: StampOptions,
): boolean {
	const raw = readFileSync(file, "utf8");
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
	const line = `${FOOTER} run=${run} (${new Date().toISOString()})\n${FOOTER_TAG} ${hits.map(h => `${h.path} (${h.score.toFixed(2)})`).join(", ")}`;
	out = `${out}\n---\n${line}\n`;
	writeFileSync(`${file}.tmp`, out);
	renameSync(`${file}.tmp`, file); // atomic swap — never a torn footer
	return true;
}