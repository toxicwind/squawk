#!/usr/bin/env bun
/**
 * bge-xref — thin entrypoint. All logic lives in src/bge-xref/ (modules):
 *   argos.ts   BM25 recall over the estate corpus (ES-wire, multi_match)
 *   embed.ts   serial full-answer embed lane + shared text-addressable qdrant cache
 *   rerank.ts  bge cosine re-rank with skill-hub mirror dedupe
 *   stamp.ts   atomic `touches:` footer writer (run= ids)
 *   lock.ts    per-todo O_EXCL lock — the single-stamp guarantee
 *   todos.ts   fleet board discovery (board SSOT = ranch/squawk/todo)
 *   index.ts   orchestration + CLI
 *
 * Two-stage hybrid, estate doctrine (LSP semanticRank pattern): BM25 recall →
 * bge re-rank → top-N real file paths stamped into each todo. Idempotent;
 * never stamps a todo twice, even under concurrent invocations.
 */
import { main } from "../src/bge-xref/index.ts";

main().catch(e => {
	console.error(e);
	process.exit(1);
});