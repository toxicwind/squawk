/**
 * embed.ts — serial full-answer embed lane with a shared text-addressable cache.
 *
 * Two Pens patterns borrowed, credited:
 *  - carryback.ts embedCached (tau-wtf): qdrant sha256(text)→UUID point cache —
 *    bge-m3 vectors are deterministic per text, so identical text never embeds
 *    twice across products (cache-friendly — the "never run more than once on
 *    the same" doctrine applied to embedding).
 *  - tau lsp/semantic.ts `embedFull` (2026-11-03 race fix, tau 4b6a7eae19):
 *    SERIAL batches + full-answer invariant + 1 retry. freeinference answers
 *    a loser of a CONCURRENT batch pair with HTTP 200 + {data:[]} (no error,
 *    empty) — Promise.all([a,b]) loses a side ~60-75% of runs. Never parallel.
 *
 * The cache is fail-open: any qdrant error falls back to a live embed, and
 * write-back is best-effort. The full-answer contract is the hard invariant.
 */
import { embedMany } from "/home/toxic/pens/barn/products/forge/hf/hf";
import { trunc } from "./trunc";

const BGE_DIM = 1024;
const QDRANT_URL = process.env.QDRANT_URL ?? "http://127.0.0.1:25133";
const QDRANT_COLLECTION = process.env.BGE_XREF_CACHE ?? "text_vectors";

export { trunc };

async function sha256Uuid(text: string): Promise<string> {
	const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
	const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
	return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}

let cacheReady = false;
async function ensureCollection(): Promise<void> {
	if (cacheReady) return;
	const res = await fetch(`${QDRANT_URL}/collections/${QDRANT_COLLECTION}`).catch(() => null);
	if (res?.ok) { cacheReady = true; return; }
	await fetch(`${QDRANT_URL}/collections/${QDRANT_COLLECTION}`, {
		method: "PUT",
		headers: { "content-type": "application/json" },
		body: JSON.stringify({ vectors: { size: BGE_DIM, distance: "Cosine" } }),
	}).catch(() => {});
	cacheReady = true; // next lookup re-probes if the PUT failed
}

/** Serial full-answer embed with retry — the hard invariant; never parallel batches. */
async function embedLive(inputs: string[]): Promise<number[][]> {
	for (let attempt = 0; attempt < 2; attempt++) {
		const vecs = await embedMany(inputs);
		if (vecs.length === inputs.length && vecs.every(v => v.length === BGE_DIM)) return vecs;
		if (attempt === 0) await new Promise(r => setTimeout(r, 900));
	}
	throw new Error(`embed short-answer after retry (${inputs.length} inputs)`);
}

/**
 * Embed with the shared text-addressable qdrant cache:
 *  - hit: vectors served from cache — zero live embed cost (run 2+ is ~50ms)
 *  - miss: serial live embed, best-effort write-back (sha256→UUID point ids)
 * Serial throughout; identical behavior to the pre-cache lane on any cache error.
 */
export async function embedCached(inputs: string[]): Promise<number[][]> {
	if (inputs.length === 0) return [];
	const keys = await Promise.all(inputs.map(sha256Uuid));
	const out: Array<number[] | null> = new Array(inputs.length).fill(null);
	try {
		await ensureCollection();
		const res = await fetch(`${QDRANT_URL}/collections/${QDRANT_COLLECTION}/points`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ ids: keys, with_payload: false, with_vector: true }),
			signal: AbortSignal.timeout(3000),
		});
		if (res.ok) {
			const j = (await res.json()) as { result: Array<{ id: string; vector: number[] }> };
			for (const p of j.result ?? []) {
				const idx = keys.indexOf(p.id);
				if (idx >= 0 && Array.isArray(p.vector) && p.vector.length === BGE_DIM) out[idx] = p.vector;
			}
		}
	} catch { /* cache read failure → live embed below */ }

	const missIdx = inputs.map((_, i) => i).filter(i => out[i] === null);
	if (missIdx.length > 0) {
		const missTexts = missIdx.map(i => inputs[i]);
		const vecs = await embedLive(missTexts);
		try {
			const points = missIdx.map((idx, k) => ({ id: keys[idx], vector: vecs[k] }));
			await fetch(`${QDRANT_URL}/collections/${QDRANT_COLLECTION}/points?wait=true`, {
				method: "PUT",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({ points }),
				signal: AbortSignal.timeout(3000),
			}).catch(() => {});
		} catch { /* write-back non-fatal */ }
		missIdx.forEach((idx, k) => { out[idx] = vecs[k]; });
	}
	return out as number[][];
}