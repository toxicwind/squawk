/**
 * argos.ts — ES-wire client for the Pens code corpus (argos :9200, pens-corpus).
 *
 * Borrowed pattern: tau-wtf audit.ts hits argos via the ES-wire `_search` API;
 * this module wraps the one query shape that WORKS there. Measured 2026-11-03:
 * argos's `query_string` parser returns 0 hits even on sanitized input —
 * `multi_match` (title^3, text, ax_path) is the reliable recall lane.
 */
import { trunc } from "./trunc";

export interface CorpusCandidate {
	/** `kind:readme/ranch/Foo/README.md` — argos index identity. */
	ax: string;
	/** BM25 relevance score from argos. */
	bm25: number;
	/** Indexed doc text, truncated for embedding. */
	text: string;
}

export interface ArgosOptions {
	base: string; // default http://127.0.0.1:9200
	index: string; // default pens-corpus
	pensRoot: string; // default /home/toxic/pens
}

const DEFAULTS: ArgosOptions = {
	base: process.env.ARGOS_URL ?? "http://127.0.0.1:9200",
	index: "pens-corpus",
	pensRoot: "/home/toxic/pens",
};

/** ax_path `kind:readme/ranch/Foo/README.md` → /home/toxic/pens/ranch/Foo/README.md */
export function realPath(ax: string, score: number, pensRoot = DEFAULTS.pensRoot): { path: string; score: number } {
	if (ax.startsWith("/")) return { path: ax, score };
	const p = ax.replace(/^kind:[a-z0-9_-]+\//i, "");
	return { path: p.startsWith("/") ? p : `${pensRoot}/${p}`, score };
}

/** BM25 recall over the corpus — multi_match (NOT query_string; argos wire). */
export async function bm25Recall(
	query: string,
	size = 50,
	opts: Partial<ArgosOptions> = {},
): Promise<CorpusCandidate[]> {
	const o = { ...DEFAULTS, ...opts };
	const r = await fetch(`${o.base}/${o.index}/_search`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		signal: AbortSignal.timeout(5000),
		body: JSON.stringify({
			size,
			query: {
				multi_match: { query: trunc(query, 200), fields: ["title^3", "text", "ax_path"] },
			},
			_source: ["ax_path", "text", "kind", "title"],
		}),
	});
	if (!r.ok) throw new Error(`argos ${r.status}: ${(await r.text()).slice(0, 120)}`);
	const d = await r.json();
	return (d.hits?.hits ?? [])
		.map((h: any) => ({
			ax: h._source?.ax_path ?? h._source?.title ?? "",
			bm25: h._score ?? 0,
			text: (h._source?.text ?? h._source?.title ?? h._source?.ax_path ?? "").slice(0, 400),
		}))
		.filter((c: any) => c.ax);
}