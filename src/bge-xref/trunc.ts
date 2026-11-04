/**
 * trunc.ts — text truncation for embed/token budgets (shared util).
 */
export function trunc(text: string, n = 400): string {
	const t = text.trim().replace(/\s+/g, " ");
	return t.length > n ? `${t.slice(0, n)}…` : t;
}