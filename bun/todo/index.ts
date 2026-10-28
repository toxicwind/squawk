// squawk/todo — first-class fleet todo board.
//
// Folder-backed (todo/*.md is the system of record) + JSON index (TODO.md)
// so any agent or human can read the queue without the daemon. The daemon
// exposes /v1/todo endpoints and MCP tools (todo_list, todo_add, todo_done)
// for first-class access. Single-writer semantics: last write wins per file,
// status parsed from the `status:` header line.

import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

export interface TodoDeps {
  todoDir: string;
}

export interface TodoItem {
  file: string;
  title: string;
  author: string;
  status: string;
  created: string;
  urgency: "normal" | "urgent";
  /** Stable id from the `unique-id:` header (when present). Resolving done
   *  by id beats file-name or title matching: titles drift, files don't. */
  uniqueId?: string;
}

const STATUS_RE = /^[-*]?\s*status:\s*(.+)$/im;
const AUTHOR_RE = /^[-*]?\s*author:\s*(.+)$/im;
const CREATED_RE = /^[-*]?\s*created:\s*(.+)$/im;
const URGENT_RE = /most urgent|urgent/i;

export function parseTodo(file: string, raw: string): TodoItem {
  const title = (
    raw.match(/^#\s*TODO\s*—?\s*(.+)$/im)?.[1] ?? file.replace(/\.md$/, "")
  ).trim();
  const status = (raw.match(STATUS_RE)?.[1] ?? "unknown").trim();
  const author = (raw.match(AUTHOR_RE)?.[1] ?? "unknown").trim();
  const created = (raw.match(CREATED_RE)?.[1] ?? "").trim();
  return {
    file,
    title: title.slice(0, 120),
    author: author.slice(0, 60),
    status: status.slice(0, 80),
    created,
    urgency:
      URGENT_RE.test(status) || URGENT_RE.test(title) ? "urgent" : "normal",
    uniqueId: raw.match(/^[-*]?\s*unique-id:\s*(.+)$/im)?.[1]?.trim(),
  };
}

export function listTodos(deps: TodoDeps): TodoItem[] {
  if (!existsSync(deps.todoDir)) return [];
  const items: TodoItem[] = [];
  for (const f of readdirSync(deps.todoDir)) {
    if (!f.endsWith(".md") || f === "TODO.md") continue;
    try {
      items.push(parseTodo(f, readFileSync(join(deps.todoDir, f), "utf8")));
    } catch {
      /* unreadable file skipped */
    }
  }
  // Urgent first, then NOT STARTED before partial before done, then newest.
  // BLOCKED sorts last-but-visible: blocked items must not sink to invisible
  // (the 2026-10-27 harness scramble lost blocked items entirely).
  const rank = (s: string) =>
    /blocked/i.test(s)
      ? 3
      : /not started/i.test(s)
      ? 0
      : /in progress|partial/i.test(s)
        ? 1
        : /done|complete/i.test(s)
          ? 2
          : 1;
  return items.sort(
    (a, b) =>
      Number(b.urgency === "urgent") - Number(a.urgency === "urgent") ||
      rank(a.status) - rank(b.status) ||
      b.created.localeCompare(a.created),
  );
}

export function regenerateIndex(deps: TodoDeps): string {
  const items = listTodos(deps);
  const lines = [
    "# FLEET TODO — INDEX (auto-generated; edit the linked files, not this)",
    "",
    `Updated: ${new Date().toISOString()}`,
    "",
    "| Urgency | Status | Author | Todo | File |",
    "|---|---|---|---|---|",
    ...items.map(
      (t) =>
        `| ${t.urgency === "urgent" ? "🔥 URGENT" : ""} | ${t.status} | ${t.author} | ${t.title} | [${t.file}](${t.file}) |`,
    ),
    "",
    "Protocol: one md per arc — `todo/<YYYYMMDDTHHMMZ>-<agent>-<slug>.md`.",
    "Read via daemon: `GET /v1/todo` · MCP tools: todo_list / todo_add / todo_done.",
    "",
  ];
  const out = lines.join("\n");
  writeFileSync(join(deps.todoDir, "TODO.md"), out);
  return out;
}

// --- wire-up helpers (called from routes) ---

export function handleList(deps: TodoDeps) {
  return { ok: true, todos: listTodos(deps) };
}

export function handleAdd(
  deps: TodoDeps,
  body: { slug: string; author: string; content: string },
) {
  const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
  const authorSlug = (body.author || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-");
  const file = `${ts}-${authorSlug}-${(body.slug || "untitled")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .slice(0, 60)}.md`;
  writeFileSync(join(deps.todoDir, file), body.content);
  regenerateIndex(deps);
  return { ok: true, file };
}

// --- resolution: done/address items — ALWAYS resolve, never reject ---

/** Resolve a todo reference to a file name. NEVER rejects a resolvable ref:
 *  exact file → exact unique-id → exact title → unique substring (id, file,
 *  then title) → deterministic best-of (open before done, then newest) with
 *  the runner-up set returned alongside. Only zero candidates is an error —
 *  there is nothing to point at. The 2026-10-27 harness scramble came from
 *  HIDDEN fuzzy picks; here ambiguity resolves LOUDLY: callers get the
 *  chosen file plus `candidates` so drift is visible, not fatal. */
export function resolveTodoRef(
  deps: TodoDeps,
  ref: string,
): { file: string; candidates?: string[] } | { error: string } {
  if (!ref?.trim()) return { error: "empty todo ref" };
  const items = listTodos(deps);
  if (!items.length) return { error: "todo board is empty" };
  const one = (t: (typeof items)[number], candidates?: string[]) => ({
    file: t.file,
    ...(candidates && candidates.length > 1 ? { candidates } : {}),
  });
  const byFile = items.filter((t) => t.file === ref || t.file === `${ref}.md`);
  if (byFile.length === 1) return one(byFile[0]!);
  const byId = items.filter((t) => t.uniqueId === ref);
  if (byId.length === 1) return one(byId[0]!);
  const norm = ref.trim().toLowerCase();
  const byTitle = items.filter((t) => t.title.trim().toLowerCase() === norm);
  if (byTitle.length === 1) return one(byTitle[0]!);
  // substring tiers: a unique hit wins outright; multi-hit falls to best-of
  for (const pool of [
    items.filter((t) => t.uniqueId?.toLowerCase().includes(norm)),
    items.filter((t) => t.file.toLowerCase().includes(norm)),
    items.filter((t) => t.title.toLowerCase().includes(norm)),
  ]) {
    if (pool.length === 1) return one(pool[0]!);
    if (pool.length > 1) {
      const cands = pool.map((t) => t.file);
      // open-before-done, then newest first (listTodos is already sorted)
      const best = pool.find((t) => !/done|complete/i.test(t.status)) ?? pool[0]!;
      return one(best, cands);
    }
  }
  return {
    error: `no todo matches '${ref}' (file, unique-id, title, substring)`,
  };
}
export interface DoneMeta {
  /** Who marked it (agent name + session id). */
  by?: string;
  /** One-line verification/evidence (command, probe, or link). */
  evidence?: string;
}

function setStatusAndAppend(
  deps: TodoDeps,
  file: string,
  status: string,
  extra?: { heading?: string; lines?: string[] },
): { ok: true; file: string } {
  const p = join(deps.todoDir, file);
  let raw = readFileSync(p, "utf8");
  if (STATUS_RE.test(raw)) {
    raw = raw.replace(STATUS_RE, (m) => m.replace(/:\s*.*$/, `: ${status}`));
  } else {
    raw = `${raw}\n- status: ${status}\n`;
  }
  if (extra?.lines?.length) {
    raw = `${raw}\n## ${extra.heading ?? "Evidence"}\n${extra.lines.map((l) => `- ${l}`).join("\n")}\n`;
  }
  writeFileSync(p, raw);
  regenerateIndex(deps);
  return { ok: true, file };
}

/** Done is a DURABLE RECORD, not a pointer flip: the status line carries who
 *  and when; an `## Done` evidence block captures the verification. Ref
 *  resolves via resolveTodoRef — best-effort, never rejecting a resolvable
 *  ref; best-of picks are recorded on the item via `resolved-via`. */
export function handleDone(
  deps: TodoDeps,
  ref: string,
  meta: DoneMeta = {},
): { ok: boolean; file?: string; error?: string } {
  const r = resolveTodoRef(deps, ref);
  if ("error" in r) return { ok: false, error: r.error };
  const when = new Date().toISOString();
  const lines = [
    `marked-by: ${meta.by ?? "daemon"}`,
    `marked-at: ${when}`,
    ...(meta.evidence ? [`evidence: ${meta.evidence}`] : []),
  ];
  if (r.candidates?.length) lines.push(`resolved-via: best-of [${r.candidates.join(", ")}]`);
  return setStatusAndAppend(
    deps,
    r.file,
    `DONE (by ${meta.by ?? "daemon"}, ${when})`,
    { heading: "Done", lines },
  );
}

/** Blocked is first-class: the reason is durable on the item, not a chat
 *  aside. Unblock = handleUpdate with a non-blocked status. */
export function handleBlock(
  deps: TodoDeps,
  ref: string,
  reason: string,
  by?: string,
): { ok: boolean; file?: string; error?: string } {
  if (!reason?.trim()) return { ok: false, error: "block requires a reason" };
  const r = resolveTodoRef(deps, ref);
  if ("error" in r) return { ok: false, error: r.error };
  const when = new Date().toISOString();
  return setStatusAndAppend(
    deps,
    r.file,
    `BLOCKED (${by ?? "daemon"}, ${when}): ${reason.trim().slice(0, 200)}`,
    {
      heading: "Blocked",
      lines: [
        `reason: ${reason.trim()}`,
        `blocked-by: ${by ?? "daemon"}`,
        `blocked-at: ${when}`,
      ],
    },
  );
}

export function handleUpdate(
  deps: TodoDeps,
  body: { file: string; status?: string; title?: string },
) {
  const p = join(deps.todoDir, body.file);
  if (!existsSync(p)) return { ok: false, error: "no such todo" };
  let raw = readFileSync(p, "utf8");
  if (body.status && STATUS_RE.test(raw)) {
    raw = raw.replace(STATUS_RE, (m) =>
      m.replace(/:\s*.*$/, `: ${body.status}`),
    );
  } else if (body.status) {
    raw = `${raw}\n- status: ${body.status}\n`;
  }
  if (body.title && /^#\s*TODO\s*—?\s*/.test(raw)) {
    raw = raw.replace(/^#\s*TODO\s*—?\s*.*/m, `# TODO — ${body.title}`);
  }
  writeFileSync(p, raw);
  regenerateIndex(deps);
  return { ok: true, file: body.file };
}
