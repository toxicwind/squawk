/**
 * rerank.ts — bge semantic re-rank over BM25 candidates, with mirror dedupe.
 *
 * Borrowed pattern: tau lsp/semantic.ts — two-stage hybrid. Structural recall
 * (BM25) returns candidates by keyword; the queried todo's MEANING is matched
 * by cosine over bge-m3 embeddings of candidate doc text, so the files that
 * actually concern the todo surface first. Purely additive: candidates come
 * from recall, semantics only re-order them.
 *
 * Dedupe (measured 2026-11-03): estate/estate-skills-hub and geode/azurite
 * index the SAME skill docs under different ax_paths — collapse to the
 * canonical azurite copy, keeping the best cosine score.
 */
import { cosine } from "/home/toxic/pens/barn/products/forge/hf/hf";
import type { CorpusCandidate } from "./argos";
import { realPath } from "./argos";
import { embedCached, trunc } from "./embed";

/** Canonical-key for dedupe: strip kind:, pens prefix, and skill-hub mirrors. */
function canonicalKey(ax: string): string {
	return ax
		.replace(/^kind:[a-z0-9_-]+\//i, "")
		.replace(/^\/home\/toxic\/pens\//, "")
		.replace(/^(estate\/estate-skills-hub|geode\/azurite)\/skills\//, "geode/azurite/skills/")
		.replace(/^geode\/azurite\/upstream\/skills-hub\//, "geode/azurite/skills/");
}

export interface RankedHit {
	path: string;
	score: number;
	bm25: number;
	ax: string;
}

/**
 * Embed the query + each candidate (cached, serial) and rank by cosine of
 * meaning; dedupe mirrors; return the top-N real file paths.
 */
export async function semanticRank(
	queryVec: number[],
	candidates: CorpusCandidate[],
	topN: number,
	pensRoot?: string,
): Promise<RankedHit[]> {
	const vecs = await embedCached(candidates.map(c => trunc(c.text, 350)));
	const seen = new Map<string, { ax: string; bm25: number; sem: number }>();
	for (const [i, c] of candidates.entries()) {
		const s = { ax: c.ax, bm25: c.bm25, sem: cosine(queryVec, vecs[i]) };
		const k = canonicalKey(c.ax);
		const prev = seen.get(k);
		if (!prev || s.sem > prev.sem) seen.set(k, s);
	}
	return [...seen.values()]
		.sort((a, b) => b.sem - a.sem)
		.slice(0, topN)
		.map(c => {
			const { path, score } = realPath(c.ax, c.sem, pensRoot);
			return { path, score, bm25: c.bm25, ax: c.ax };
		});
}