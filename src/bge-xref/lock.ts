/**
 * lock.ts — per-target exclusive lock (O_EXCL) for single-stamp guarantees.
 *
 * Estate pattern (2026-11-03, squawk b8eb9ef): a check-then-act guard has a
 * TOCTOU hole — two concurrent invocations can both pass the check before
 * either writes. `withFileLock` wraps the ENTIRE read→check→write cycle under
 * an exclusive `<target>.xref.lock`:
 *  - O_EXCL open = atomic acquisition (no exists-then-create race)
 *  - crashed holder stolen after 60s (staleness by mtime)
 *  - 5×400ms retry loop, then fail loudly (never double-run)
 */
import { openSync, writeFileSync, closeSync, unlinkSync, statSync } from "node:fs";

export const LOCK_STALE_MS = 60_000;
export const LOCK_RETRIES = 5;
export const LOCK_RETRY_MS = 400;

function acquire(lockPath: string): boolean {
	try {
		const fd = openSync(lockPath, "wx");
		writeFileSync(fd, String(process.pid));
		closeSync(fd);
		return true;
	} catch {
		try {
			if (Date.now() - statSync(lockPath).mtimeMs > LOCK_STALE_MS) {
				unlinkSync(lockPath);
				return acquire(lockPath);
			}
		} catch {}
		return false;
	}
}

/** Run fn under an exclusive per-target lock; never runs fn twice on the same target. */
export async function withFileLock<T>(target: string, fn: () => Promise<T> | T): Promise<T> {
	const lockPath = `${target}.xref.lock`;
	for (let attempt = 0; attempt < LOCK_RETRIES; attempt++) {
		if (acquire(lockPath)) {
			try {
				return await fn();
			} finally {
				try { unlinkSync(lockPath); } catch {}
			}
		}
		await new Promise(r => setTimeout(r, LOCK_RETRY_MS));
	}
	throw new Error(`lock busy (${LOCK_RETRIES}×${LOCK_RETRY_MS}ms): ${lockPath} — another xref run is stamping this target`);
}